"""Replay gate (P2.2.1). Four checks, one `verdicts` doc, candidate -> passed | failed.

(a) unit        forged tests run in the sandbox (testkit program, entry "run_tests")
(b) replay      each evidence session's real inputs -> tool -> compared with that session's
                real outputs: tables exact (float tolerance), charts structural
(c) side_effects dry-run intended writes must be covered by the declared scopes
(d) duplicate   dedupe decision via search_tools: merge (>= merge_similarity, fails) ·
                adapt (>= T_high, passes, similar tool recorded) · new
"""
from __future__ import annotations

import asyncio
import csv
import json
import math
import re
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

from app.forge import deps
from app.forge.spec import input_names, resolve_artifact
from app.gate.testkit import build_test_program
from app.sandbox import run_in_sandbox

FLOAT_TOL = 0.01
DEFAULT_MERGE_SIMILARITY = 0.90
DEFAULT_T_HIGH = 0.82
UNIT_TIMEOUT_S = 60
REPLAY_TIMEOUT_S = 60  # cold pandas import in a fresh process is slow on a loaded laptop


async def run_gate(candidate_id: str) -> dict:
    db = deps.get_db()
    cand = await db.candidates.find_one({"_id": candidate_id})
    if not cand:
        raise ValueError(f"candidate {candidate_id} not found")
    t0 = time.monotonic()
    unit, replay, dup = await asyncio.gather(check_unit(cand), check_replay(cand, await _deps_for(cand)),
                                             check_duplicate(cand))
    side = check_side_effects(cand, replay.pop("_writes", []))
    checks = {"unit": unit, "replay": replay, "side_effects": side, "duplicate": dup}
    failed = [name for name, c in checks.items() if not c["ok"]]
    verdict = {
        "_id": "ver_" + secrets.token_hex(4), "candidate_id": candidate_id, "user_id": cand["user_id"],
        "tool_id": cand.get("tool_id"), "candidate_version": cand.get("attempt_no", 1),
        "checks": checks, "decision": "failed" if failed else "passed",
        "reason": "; ".join(f"{n}: {checks[n]['reason']}" for n in failed) or "all checks passed",
        "duration_ms": int((time.monotonic() - t0) * 1000), "created_at": datetime.now(UTC),
    }
    await db.verdicts.insert_one(verdict)
    await db.candidates.update_one({"_id": candidate_id},
                                   {"$set": {"status": verdict["decision"], "verdict_id": verdict["_id"]}})
    await deps.publish(cand["user_id"], "gate_passed" if not failed else "gate_failed", {
        "candidate_id": candidate_id, "verdict_id": verdict["_id"], "reason": verdict["reason"],
        "checks": {n: c["ok"] for n, c in checks.items()}, "dedupe": dup["decision"],
        "similar_tool": dup["top_hit"] if dup["decision"] != "new" else None,
        "replay_cases": [{"label": c["label"], "ok": c["ok"]} for c in replay["cases"]]})
    return verdict


# ---- (a) unit ----------------------------------------------------------------

async def check_unit(cand: dict) -> dict:
    if not cand.get("code") or not cand.get("tests"):
        return {"ok": False, "reason": "no code or tests", "total": 0, "passed": 0, "failed": []}
    r = await run_in_sandbox(build_test_program(cand["code"], cand["tests"]), "run_tests", {}, {},
                             "dry_run", [], timeout_s=UNIT_TIMEOUT_S)
    if not r.ok:
        return {"ok": False, "reason": f"tests crashed: {_short(r.error)}", "total": 0, "passed": 0, "failed": []}
    out = r.output
    ok = out.get("total", 0) > 0 and not out.get("failed")
    reason = "" if ok else ("no tests" if not out.get("total") else
                            f"{len(out['failed'])}/{out['total']} failed: {out['failed'][0]['name']}: "
                            f"{out['failed'][0]['error']}")
    return {"ok": ok, "reason": reason, "total": out.get("total", 0), "passed": out.get("passed", 0),
            "failed": out.get("failed", [])}


# ---- (b) replay --------------------------------------------------------------

async def replay_cases(cand: dict) -> list[dict]:
    """[{label, inputs: {name: path}, params, expected: {tables: {name: csv}, chart: json|None}}]
    From the evidence sessions' `artifacts` (inputs + outputs); falls back to the candidate's
    evidence inputs + the `expected/<stem>_*` convention next to them.
    A candidate may carry explicit `replay_cases` (heal: old fixtures + the new failing page);
    their `expected.tables` values may be inline rows, inputs may be literal text."""
    if cand.get("replay_cases"):
        return cand["replay_cases"]
    spec = cand.get("spec") or {}
    names = input_names(spec)
    sessions = []
    ids = (cand.get("origin") or {}).get("evidence_session_ids") or []
    if ids:
        sessions = [s async for s in deps.get_db().sessions.find({"_id": {"$in": ids}})]
        sessions.sort(key=lambda s: ids.index(s["_id"]))
    cases = []
    for s in sessions:
        arts = s.get("artifacts") or {}
        ins = [_path(i) for i in arts.get("inputs", [])]
        outs = [_path(o) for o in arts.get("outputs", [])] or (_expected_for(ins[0]) if ins else [])
        if ins:
            cases.append(_case(s["_id"], ins, outs, names, spec, s.get("params") or {}))
    if not cases:
        for p in cand.get("evidence_inputs") or []:
            cases.append(_case(Path(p).stem, [p], _expected_for(p), names, spec, {}))
    return cases


def _case(label, ins, outs, names, spec, session_params) -> dict:
    inputs = dict(zip(names, ins, strict=False))
    tables = {_table_name(o): o for o in outs if o.endswith(".csv")}
    chart = next((o for o in outs if o.endswith(".json") and "chart" in Path(o).name), None)
    extracted = next((o for o in outs if o.endswith("_params.json")), None)  # UC2: extracted param keys
    return {"label": label, "inputs": inputs, "params": _params_for(spec, ins[0], session_params),
            "expected": {"tables": tables, "chart": chart, "params": extracted}}


def _path(item) -> str:
    return item.get("path") if isinstance(item, dict) else item


def _expected_for(input_path: str) -> list[str]:
    p = resolve_artifact(input_path)
    return sorted(str(q) for q in (p.parent / "expected").glob(f"{p.stem}_*") if q.suffix in {".csv", ".json"})


def _table_name(path: str) -> str:
    stem = Path(path).stem
    return stem.split("_", 1)[1] if "_" in stem else stem


def _params_for(spec: dict, input_path: str, session_params: dict) -> dict:
    params = {}
    for name, p in spec.get("params_schema", {}).get("properties", {}).items():
        if p.get("format") == "file":  # the value is the input's handle: read_table(params["file"]) works
            params[name] = name
            continue
        if name in session_params:
            params[name] = session_params[name]
        elif m := re.search(rf"{re.escape(name)}[_-]?(\d+)", Path(input_path).stem, re.IGNORECASE):
            params[name] = m.group(1)
        elif "default" in p:
            params[name] = p["default"]
        else:
            params[name] = ""
    return params


async def _deps_for(cand: dict) -> dict[str, str] | Exception:
    """Composed tools: code of every `requires.tools` dependency, mounted for ctx.call."""
    names = (cand.get("requires") or {}).get("tools") or []
    if not names:
        return {}
    try:
        return await deps.dependency_code(cand["user_id"], names)
    except deps.MissingDependency as e:
        return e


async def check_replay(cand: dict, dep_code: dict[str, str] | Exception | None = None) -> dict:
    if isinstance(dep_code, Exception):  # fail closed
        return {"ok": False, "reason": str(dep_code), "cases": [], "_writes": []}
    cases = await replay_cases(cand)
    if not cases:
        return {"ok": False, "reason": "no evidence artifacts to replay", "cases": [], "_writes": []}
    scopes = (cand.get("requires") or {}).get("scopes", [])
    runs = await asyncio.gather(*[
        run_in_sandbox(cand["code"], "run", c["params"], {k: _input_value(v) for k, v in c["inputs"].items()},
                       "dry_run", scopes, timeout_s=REPLAY_TIMEOUT_S, deps=dep_code or None) for c in cases])
    results, writes = [], []
    for case, r in zip(cases, runs, strict=True):
        diffs = [f"run failed: {_short(r.error)}"] if not r.ok else compare_output(r.output, case["expected"])
        writes += [w.path if not w.kind.startswith("action:") else w.kind for w in r.intended_writes]
        results.append({"label": case["label"], "ok": not diffs, "diffs": diffs[:5], "params": case["params"],
                        "inputs": {k: _input_label(v) for k, v in case["inputs"].items()},
                        "duration_ms": r.duration_ms,
                        "summary": (r.output or {}).get("summary") if r.ok else None})
    bad = [c for c in results if not c["ok"]]
    reason = "" if not bad else f"{len(bad)}/{len(results)} cases differ; {bad[0]['label']}: {bad[0]['diffs'][0]}"
    return {"ok": not bad, "reason": reason, "cases": results, "_writes": writes}


def _looks_like_path(v: str) -> bool:
    return isinstance(v, str) and len(v) < 400 and "\n" not in v and resolve_artifact(v).is_file()


def _input_value(v: str) -> str:
    """Artifact paths resolve against the repo; anything else is literal content (e.g. a fetch map)."""
    return str(resolve_artifact(v)) if _looks_like_path(v) else v


def _input_label(v: str) -> str:
    return Path(v).name if _looks_like_path(v) else f"<{len(v)} chars>"


def compare_output(output: dict, expected: dict) -> list[str]:
    diffs = []
    got_tables = output.get("tables") or {}
    for name, exp_rows in expected.get("tables", {}).items():
        got = got_tables.get(name)
        if got is None and len(got_tables) == 1:
            got = next(iter(got_tables.values()))
        if got is None:
            diffs.append(f"table '{name}' missing from output")
            continue
        exp = exp_rows if isinstance(exp_rows, list) else _read_csv(exp_rows)
        diffs += [f"table '{name}': {d}" for d in compare_table(got, exp)]
    if expected.get("chart"):
        exp = json.loads(resolve_artifact(expected["chart"]).read_text(encoding="utf-8"))
        diffs += [f"chart: {d}" for d in compare_chart(output.get("chart_spec"), exp)]
    if expected.get("params"):
        exp = expected["params"]
        exp = exp if isinstance(exp, dict) else json.loads(resolve_artifact(exp).read_text(encoding="utf-8"))
        diffs += [f"params: {d}" for d in compare_params(output.get("params"), exp)]
    return diffs


def compare_params(got: dict | None, exp: dict) -> list[str]:
    """Extracted key/value params (UC2): same keys, values equal after whitespace normalisation."""
    if not isinstance(got, dict):
        return ["no params in output"]
    diffs = [f"missing key {k!r}" for k in exp if k not in got]
    for k in exp:
        if k in got and " ".join(str(got[k]).split()) != " ".join(str(exp[k]).split()):
            diffs.append(f"{k!r}: {str(got[k])[:80]!r} != expected {str(exp[k])[:80]!r}")
    return diffs


def compare_table(got: list[dict], exp: list[dict]) -> list[str]:
    if not isinstance(got, list):
        return [f"expected a list of rows, got {type(got).__name__}"]
    if not exp:
        return [] if not got else [f"expected 0 rows, got {len(got)}"]
    exp_cols = list(exp[0])
    got_cols = list(got[0]) if got else []
    if set(got_cols) != set(exp_cols):
        return [f"columns {got_cols} != expected {exp_cols}"]
    if len(got) != len(exp):
        return [f"{len(got)} rows != expected {len(exp)}"]
    key = exp_cols[0]
    got = sorted(got, key=lambda r: str(r[key]))
    exp = sorted(exp, key=lambda r: str(r[key]))
    diffs = []
    for g, e in zip(got, exp, strict=True):
        for c in exp_cols:
            if not _same(g[c], e[c]):
                diffs.append(f"row {e[key]!r} col {c!r}: {g[c]!r} != expected {e[c]!r}")
    return diffs


def compare_chart(got: dict | None, exp: dict) -> list[str]:
    if not isinstance(got, dict):
        return ["no chart_spec in output"]
    diffs = []
    if got.get("type") != exp.get("type"):
        diffs.append(f"type {got.get('type')!r} != {exp.get('type')!r}")
    if [str(x) for x in got.get("x", [])] != [str(x) for x in exp.get("x", [])]:
        diffs.append(f"x {got.get('x')} != {exp.get('x')}")
    gy, ey = got.get("y", []), exp.get("y", [])
    if len(gy) != len(ey) or not all(_same(a, b) for a, b in zip(gy, ey, strict=False)):
        diffs.append(f"y {gy} != {ey}")
    return diffs


def _same(a, b) -> bool:
    fa, fb = _num(a), _num(b)
    if fa is not None and fb is not None:
        return math.isclose(fa, fb, abs_tol=FLOAT_TOL)
    return str(a).strip() == str(b).strip()


def _num(v) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _read_csv(path: str) -> list[dict]:
    with resolve_artifact(path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ---- (c) side effects --------------------------------------------------------

def check_side_effects(cand: dict, writes: list[str]) -> dict:
    """Files need write:outputs (and must be declared); `action:<app>.<verb>` needs app:<app>."""
    scopes = set((cand.get("requires") or {}).get("scopes", []))
    violations = []
    actions = sorted({w for w in writes if w.startswith("action:")})
    files = [w for w in writes if not w.startswith("action:")]
    if files and "write:outputs" not in scopes:
        violations.append(f"writes {sorted(set(files))} without the write:outputs scope")
    declared = set((cand.get("spec") or {}).get("outputs", {}).get("files", []))
    if declared and (extra := sorted(set(files) - declared)):
        violations.append(f"undeclared output files {extra}")
    for action in actions:
        app = action.removeprefix("action:").split(".", 1)[0]
        if f"app:{app}" not in scopes:
            violations.append(f"{action} without the app:{app} scope")
    return {"ok": not violations, "reason": "; ".join(violations), "writes": sorted(set(files)),
            "actions": actions, "scopes": sorted(scopes)}


# ---- (d) duplicate -----------------------------------------------------------

async def check_duplicate(cand: dict) -> dict:
    spec = cand.get("spec") or {}
    query = " ".join(filter(None, [spec.get("title"), spec.get("purpose"), " ".join(spec.get("keywords", []))]))
    threshold, t_high = await _dedupe_thresholds(cand["user_id"])
    hits = await deps.search_tools(cand["user_id"], query, 3) if query else []
    top = hits[0] if hits else None
    top_d = _hit_dict(top) if top else None
    other = bool(top_d and top_d["tool_id"] != cand.get("tool_id"))  # a heal's own tool is not a duplicate
    score = top_d["score"] if other else 0.0
    # merge: same tool already exists (fail, merge path) · adapt: a close tool exists, new one
    # still allowed (recorded so the UI can say "similar to Y") · new: nothing close
    decision = "merge" if score >= threshold else "adapt" if score >= t_high else "new"
    return {"ok": decision != "merge", "decision": decision,
            "reason": f"duplicate of {top_d['name']} (score {score:.2f})" if decision == "merge" else "",
            "top_hit": top_d, "threshold": threshold, "adapt_threshold": t_high}


async def _dedupe_thresholds(user_id: str) -> tuple[float, float]:
    pol = await deps.get_db().policy.find_one({"_id": f"policy:{user_id}"})
    th = (pol or {}).get("thresholds") or {}
    return float(th.get("merge_similarity", DEFAULT_MERGE_SIMILARITY)), float(th.get("T_high", DEFAULT_T_HIGH))


def _hit_dict(h) -> dict:
    get = h.get if isinstance(h, dict) else (lambda k, d=None: getattr(h, k, d))
    return {"tool_id": get("tool_id"), "name": get("name"), "score": float(get("score", 0.0) or 0.0)}


def _short(s: str | None, n: int = 300) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else "…" + s[-n:]
