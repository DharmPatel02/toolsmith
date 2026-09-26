"""Worker job `forge` (P2.2.2): forge -> gate -> repair (<= 3) -> passed | failed.

Registered with P1's worker through `JOBS` / `register(register_fn)`.
Payload: {"pattern_id"} | {"pattern": {...}} | {"candidate_id"} (re-gate an existing candidate).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.forge import deps
from app.forge.codegen import code_prompt, repair_loop
from app.forge.service import cost_of, forge_from_pattern, forge_from_pattern_doc
from app.forge.spec import profile_inputs
from app.forge.tutorial import write_tutorial
from app.gate.service import run_gate
from app.prompts.forge_prompts import CODE_PROMPT

log = logging.getLogger(__name__)
MAX_GATE_REPAIRS = 3
FIXABLE = ("unit", "replay")  # a duplicate or a scope problem is not fixed by rewriting code


async def handle_forge(job: dict) -> dict:
    payload = job.get("payload", job)
    if payload.get("candidate_id"):
        cid = payload["candidate_id"]
    elif payload.get("pattern"):
        cid = await forge_from_pattern_doc(payload["pattern"])
    else:
        cid = await forge_from_pattern(payload["pattern_id"])
    return await gate_with_repairs(cid)


async def gate_with_repairs(cid: str, max_repairs: int = MAX_GATE_REPAIRS) -> dict:
    db = deps.get_db()
    cand = await db.candidates.find_one({"_id": cid})
    if cand["status"] not in ("gating", "failed") or not cand.get("code"):
        return {"candidate_id": cid, "status": cand["status"]}

    for attempt in range(max_repairs + 1):
        verdict = await run_gate(cid)
        if verdict["decision"] == "passed":
            await refresh_tutorial(cid, verdict)
            return {"candidate_id": cid, "status": "passed", "verdict_id": verdict["_id"], "gate_attempts": attempt + 1}
        failed = [n for n, c in verdict["checks"].items() if not c["ok"]]
        if attempt == max_repairs or any(n not in FIXABLE for n in failed):
            break
        log.info("gate failed for %s (%s), repair %d", cid, verdict["reason"], attempt + 1)
        if not await repair_from_verdict(cid, verdict):
            break
    return {"candidate_id": cid, "status": "failed", "verdict_id": verdict["_id"], "reason": verdict["reason"]}


async def repair_from_verdict(cid: str, verdict: dict) -> bool:
    db = deps.get_db()
    cand = await db.candidates.find_one({"_id": cid})
    pattern = {}
    if cand.get("pattern_id"):
        pattern = await db.patterns.find_one({"_id": cand["pattern_id"]}) or {}
    pattern = pattern or cand.get("origin") or {}
    profiles = profile_inputs(cand.get("evidence_inputs") or [])
    messages = [
        {"role": "system", "content": CODE_PROMPT},
        {"role": "user", "content": code_prompt(cand["spec"], pattern, profiles)},
        {"role": "assistant", "content": json.dumps({"code": cand["code"], "tests": cand["tests"]})},
        {"role": "user", "content": "The replay gate FAILED on real past data. Fix the code (and tests if they "
                                    "are wrong) so the real outputs match. Details:\n" + gate_feedback(verdict)},
    ]
    res = await repair_loop(messages, cand["spec"])
    cost = cost_of(res.usage)
    old = cand.get("cost") or {}
    await db.candidates.update_one({"_id": cid}, {"$set": {
        "code": res.code, "tests": res.tests, "problems": res.problems,
        "status": "gating" if res.ok else "failed", "attempt_no": cand.get("attempt_no", 1) + 1,
        "cost": {k: round(old.get(k, 0) + cost[k], 6) for k in cost},
    }})
    return res.ok


def gate_feedback(verdict: dict) -> str:
    c = verdict["checks"]
    lines = [f"Reason: {verdict['reason']}"]
    for f in c["unit"].get("failed", [])[:3]:
        lines.append(f"- unit test {f['name']}: {f['error']}")
    for case in c["replay"].get("cases", []):
        if not case["ok"]:
            lines.append(f"- replay {case['label']} (inputs {case['inputs']}, params {case['params']}): "
                         + " | ".join(case["diffs"][:3]))
    return "\n".join(lines)


async def refresh_tutorial(cid: str, verdict: dict) -> None:
    """Rewrite TOOL.md with the example from a real passing replay (plan §6.3)."""
    db = deps.get_db()
    cand = await db.candidates.find_one({"_id": cid})
    cases = [c for c in verdict["checks"]["replay"]["cases"] if c["ok"]]
    if not cases:
        return
    ex = cases[-1]
    example = {"inputs": {**ex["params"], **ex["inputs"]},  # real file names over the input handles
               "result": ex.get("summary"), "source": f"replay of {ex['label']}"}
    try:
        md, _ = await write_tutorial(cand["spec"], example)
    except Exception:  # keep the forge-time tutorial if the model is down
        log.exception("tutorial refresh failed for %s", cid)
        return
    await db.candidates.update_one({"_id": cid}, {"$set": {"tutorial_md": md, "tutorial_example": example}})


JOBS = {"forge": handle_forge}


def register(register_fn) -> None:
    """For P1's worker: `register(job_type, handler)`."""
    for job_type, handler in JOBS.items():
        register_fn(job_type, handler)
