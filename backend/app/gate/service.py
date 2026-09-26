"""Replay gate (P2.2.1). Four checks, one `verdicts` doc, candidate -> passed | failed.

(a) unit        forged tests run in the sandbox (testkit program, entry "run_tests")
(b) replay      each evidence session's real inputs -> tool -> compared with that session's
                real outputs: tables exact (float tolerance), charts structural
(c) side_effects dry-run intended writes must be covered by the declared scopes
(d) duplicate   an existing tool that already does this (search_tools score >= merge_similarity)
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
UNIT_TIMEOUT_S = 60
REPLAY_TIMEOUT_S = 60  # cold pandas import in a fresh process is slow on a loaded laptop


async def run_gate(candidate_id: str) -> dict:
    db = deps.get_db()
    cand = await db.candidates.find_one({"_id": candidate_id})
    if not cand:
        raise ValueError(f"candidate {candidate_id} not found")
    t0 = time.monotonic()
    unit, replay, dup = await asyncio.gather(check_unit(cand), check_replay(cand), check_duplicate(cand))
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
        "checks": {n: c["ok"] for n, c in checks.items()},
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
    evidence inputs + the `expected/<stem>_*` convention next to them."""
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
    return {"label": label, "inputs": inputs, "params": _params_for(spec, ins[0], session_params),
            "expected": {"tables": tables, "chart": chart}}


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
        if p.get("format") == "file":
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


async def check_replay(cand: dict) -> dict:
    cases = await replay_cases(cand)
    if not cases:
        return {"ok": False, "reason": "no evidence artifacts to replay", "cases": [], "_writes": []}
    scopes = (cand.get("requires") or {}).get("scopes", [])
    runs = await asyncio.gather(*[
        run_in_sandbox(cand["code"], "run", c["params"], {k: str(resolve_artifact(v)) for k, v in c["inputs"].items()},
                       "dry_run", scopes, timeout_s=REPLAY_TIMEOUT_S) for c in cases])
    results, writes = [], []
    for case, r in zip(cases, runs, strict=True):
        diffs = [f"run failed: {_short(r.error)}"] if not r.ok else compare_output(r.output, case["expected"])
        writes += [w.path for w in r.intended_writes]
        results.append({"label": case["label"], "ok": not diffs, "diffs": diffs[:5], "params": case["params"],
                        "inputs": {k: Path(v).name for k, v in case["inputs"].items()},
                        "duration_ms": r.duration_ms,
                        "summary": (r.output or {}).get("summary") if r.ok else None})
    bad = [c for c in results if not c["ok"]]
    reason = "" if not bad else f"{len(bad)}/{len(results)} cases differ; {bad[0]['label']}: {bad[0]['diffs'][0]}"
    return {"ok": not bad, "reason": reason, "cases": results, "_writes": writes}


def compare_output(output: dict, expected: dict) -> list[str]:
    diffs = []
    got_tables = output.get("tables") or {}
    for name, csv_path in expected.get("tables", {}).items():
        got = got_tables.get(name)
        if got is None and len(got_tables) == 1:
            got = next(iter(got_tables.values()))
        if got is None:
            diffs.append(f"table '{name}' missing from output")
            continue
        diffs += [f"table '{name}': {d}" for d in compare_table(got, _read_csv(csv_path))]
    if expected.get("chart"):
        exp = json.loads(resolve_artifact(expected["chart"]).read_text(encoding="utf-8"))
        diffs += [f"chart: {d}" for d in compare_chart(output.get("chart_spec"), exp)]
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
    scopes = set((cand.get("requires") or {}).get("scopes", []))
    violations = []
    if writes and "write:outputs" not in scopes:
        violations.append(f"writes {sorted(set(writes))} without the write:outputs scope")
    declared = set((cand.get("spec") or {}).get("outputs", {}).get("files", []))
    if declared and (extra := sorted(set(writes) - declared)):
        violations.append(f"undeclared output files {extra}")
    return {"ok": not violations, "reason": "; ".join(violations), "writes": sorted(set(writes)),
            "scopes": sorted(scopes)}


# ---- (d) duplicate -----------------------------------------------------------

async def check_duplicate(cand: dict) -> dict:
    spec = cand.get("spec") or {}
    query = " ".join(filter(None, [spec.get("title"), spec.get("purpose"), " ".join(spec.get("keywords", []))]))
    threshold = await _merge_similarity(cand["user_id"])
    hits = await deps.search_tools(cand["user_id"], query, 3) if query else []
    top = hits[0] if hits else None
    top_d = _hit_dict(top) if top else None
    is_dup = bool(top_d and top_d["score"] >= threshold and top_d["tool_id"] != cand.get("tool_id"))
    return {"ok": not is_dup, "reason": f"duplicate of {top_d['name']} (score {top_d['score']:.2f})" if is_dup else "",
            "top_hit": top_d, "threshold": threshold}


async def _merge_similarity(user_id: str) -> float:
    pol = await deps.get_db().policy.find_one({"_id": f"policy:{user_id}"})
    return float(((pol or {}).get("thresholds") or {}).get("merge_similarity", DEFAULT_MERGE_SIMILARITY))


def _hit_dict(h) -> dict:
    get = h.get if isinstance(h, dict) else (lambda k, d=None: getattr(h, k, d))
    return {"tool_id": get("tool_id"), "name": get("name"), "score": float(get("score", 0.0) or 0.0)}


def _short(s: str | None, n: int = 300) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else "…" + s[-n:]
