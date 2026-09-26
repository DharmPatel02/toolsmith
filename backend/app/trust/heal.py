"""Heal (P2.3.2): a drifting web tool -> capture the failing page -> diagnose (heavy model) ->
version v+1 -> gate on the new page AND the old fixtures -> promote at `dry_run` -> `healed`.

Assumption (mock site contract): the data didn't change, only the layout, so the new page's
expected output is the old fixture's expected output. Time-to-heal runs from drift detection
(or the heal start) to promotion.
"""
from __future__ import annotations

import json
import logging
import secrets
import time
from datetime import UTC, datetime

import httpx

from app import llm
from app.forge import deps
from app.forge.checks import check_tests, check_tool_code
from app.forge.jobs import gate_feedback
from app.forge.service import cost_of
from app.gate.service import compare_output, run_gate
from app.prompts.forge_prompts import REPAIR_PROMPT
from app.prompts.heal_prompts import HEAL_PROMPT, HEAL_SCHEMA, heal_user_message
from app.sandbox import run_in_sandbox
from app.sandbox.harness import FETCH_MAP_INPUT
from app.trust import uc3_seed
from app.trust.promote import promote

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


class HealError(RuntimeError):
    pass


async def heal_tool(tool_id: str, detected_at: datetime | str | None = None,
                    failing_run_ids: list[str] | None = None) -> dict:
    db = deps.get_db()
    t0 = time.monotonic()
    started = _as_dt(detected_at) or datetime.now(UTC)
    tool = await db.tools.find_one({"_id": tool_id})
    if not tool:
        raise HealError(f"tool {tool_id} not found")
    user_id = tool["user_id"]
    version = await db.tool_versions.find_one({"_id": f"{tool_id}@v{tool['active_version']}"})
    old_cases = ((version or {}).get("fixtures_ref") or {}).get("replay_cases") or []
    web_cases = [c for c in old_cases if FETCH_MAP_INPUT in c.get("inputs", {})]
    if not web_cases:
        raise HealError(f"{tool_id} has no recorded web fixtures to heal against")

    old = web_cases[0]
    url = await _failing_url(failing_run_ids) or old["params"].get("url")
    new_page, page_source = await capture_page(url, tool_id)
    new_case = {"label": f"heal_{datetime.now(UTC):%H%M%S}", "inputs": {FETCH_MAP_INPUT: json.dumps({url: new_page})},
                "params": {**old["params"], "url": url}, "expected": old["expected"]}
    scopes = version["requires"].get("scopes", [])

    # reproduce on the captured page: the diagnosis needs the real error, and a page that
    # still works means there is nothing to heal (e.g. a flaky network)
    repro = await run_in_sandbox(version["code"], "run", new_case["params"], new_case["inputs"], "dry_run", scopes)
    if repro.ok and not compare_output(repro.output, old["expected"]):
        await db.tools.update_one({"_id": tool_id}, {"$set": {"drift.active": False}})
        return {"tool_id": tool_id, "status": "not_reproduced", "page_source": page_source}
    error = repro.error or f"wrong output: {json.dumps(repro.output.get('tables'))[:800]}"

    await deps.publish(user_id, "forge_started", {"tool_id": tool_id, "kind": "heal", "title": tool.get("title")})
    old_input = json.loads(old["inputs"][FETCH_MAP_INPUT]).get(old["params"].get("url"), "")
    messages = [{"role": "system", "content": HEAL_PROMPT},
                {"role": "user", "content": heal_user_message(version["code"], version.get("tests") or "", error,
                                                              old_input, new_page,
                                                              json.dumps(old["expected"]["tables"]))}]
    cid = "cand_" + secrets.token_hex(4)
    spec = version.get("spec") or _spec_from(tool, version)
    usage: list[llm.LLMResult] = []
    verdict = None
    diagnosis = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        res = await llm.complete("heavy", messages, HEAL_SCHEMA, max_tokens=8192)
        usage.append(res)
        diagnosis, code, tests = res.json["diagnosis"], res.json["code"], res.json["tests"]
        problems = check_tool_code(code, spec.get("requires", {}).get("deps")) + check_tests(tests)
        messages = messages + [{"role": "assistant", "content": res.text or json.dumps(res.json)}]
        if problems:
            messages.append({"role": "user", "content": REPAIR_PROMPT.format(
                problems="\n".join(f"- {p}" for p in problems)) + ' Keep the "diagnosis" field.'})
            continue
        await _save_candidate(cid, user_id, tool, version, spec, code, tests, [*old_cases, new_case],
                              diagnosis, error, page_source, attempt, usage)
        verdict = await run_gate(cid)
        if verdict["decision"] == "passed":
            break
        messages.append({"role": "user", "content": "The gate FAILED. Fix it so both OLD and NEW pass.\n"
                                                    + gate_feedback(verdict)})

    if verdict is None or verdict["decision"] != "passed":
        reason = verdict["reason"] if verdict else "code never passed static checks"
        await db.tools.update_one({"_id": tool_id}, {"$set": {"drift.heal_failed": reason}})
        log.warning("heal of %s failed: %s", tool_id, reason)
        return {"tool_id": tool_id, "status": "failed", "candidate_id": cid if verdict else None, "reason": reason}

    await promote(cid, user_id)
    new_version = tool["active_version"] + 1
    ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    heal = {"version": new_version, "candidate_id": cid, "diagnosis": diagnosis, "time_to_heal_ms": ms,
            "heal_ms": int((time.monotonic() - t0) * 1000), "page_source": page_source,
            "cost": cost_of(usage), "at": datetime.now(UTC)}
    await db.tools.update_one({"_id": tool_id}, {"$set": {"drift.active": False, "last_heal": heal},
                                                 "$push": {"heals": heal}})
    await deps.publish(user_id, "healed", {"tool_id": tool_id, "name": tool.get("name"), "version": new_version,
                                           "candidate_id": cid, "diagnosis": diagnosis, "time_to_heal_ms": ms,
                                           "trust": "dry_run"})
    return {"tool_id": tool_id, "status": "healed", **{k: v for k, v in heal.items() if k != "at"}}


async def capture_page(url: str, tool_id: str) -> tuple[str, str]:
    """The page as the tool sees it now: live, else P3's v2 snapshot (UC3 only)."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.text, "live"
    except httpx.HTTPError as e:
        if tool_id != uc3_seed.TOOL_ID:
            raise HealError(f"cannot capture {url}: {e}") from e
        log.warning("live capture of %s failed (%s); using the v2 snapshot", url, e)
        return uc3_seed.snapshot("v2"), "snapshot"


async def _failing_url(run_ids: list[str] | None) -> str | None:
    if not run_ids:
        return None
    run = await deps.get_db().runs.find_one({"_id": {"$in": run_ids}})
    return ((run or {}).get("params") or {}).get("url")


async def _save_candidate(cid, user_id, tool, version, spec, code, tests, cases, diagnosis, error, page_source,
                          attempt, usage) -> None:
    doc = {"_id": cid, "user_id": user_id, "tool_id": tool["_id"], "pattern_id": None, "idea_id": None,
           "origin": {"kind": "heal", "tool_id": tool["_id"], "from_version": tool["active_version"],
                      "evidence_session_ids": []},
           "spec": spec, "params_schema": version["params_schema"], "requires": version["requires"],
           "derivation": version["derivation"], "tutorial_md": version.get("tutorial_md"),
           "code": code, "tests": tests, "replay_cases": cases, "problems": [], "status": "gating",
           "attempt_no": attempt, "verdict_id": None, "cost": cost_of(usage),
           "heal": {"diagnosis": diagnosis, "error": error[-2000:], "page_source": page_source},
           "created_at": datetime.now(UTC)}
    await deps.get_db().candidates.replace_one({"_id": cid}, doc, upsert=True)
    await deps.publish(user_id, "forged", {"candidate_id": cid, "tool_id": tool["_id"], "kind": "heal",
                                           "status": "gating", "name": spec["name"], "diagnosis": diagnosis})


def _spec_from(tool: dict, version: dict) -> dict:
    return {"name": tool["name"], "title": tool.get("title", tool["name"]), "purpose": tool.get("title", ""),
            "keywords": tool.get("keywords", []), "params_schema": version["params_schema"],
            "requires": version["requires"], "derivation": version["derivation"], "outputs": {"files": []}}


def _as_dt(v) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v if v is None or v.tzinfo else v.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
