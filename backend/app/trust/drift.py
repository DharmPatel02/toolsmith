"""Drift watcher (P2.3.1): a tool's last runs vs its baseline -> `drift_detected` + heal job.

Drift = the latest FAIL_STREAK runs all failed, or the success rate of the last WINDOW
runs fell more than RATE_DROP below the tool's baseline success rate. One open heal per
tool: while a heal job is queued/running, check_drift reports drift but queues nothing.
P1's worker calls this from the `runs` change stream.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.forge import deps

WINDOW = 10
FAIL_STREAK = 3
RATE_DROP = 0.3
MIN_RUNS_FOR_RATE = 5


def run_ok(run: dict) -> bool | None:
    """True / False for a finished run, None if it doesn't count (preview not confirmed, etc.)."""
    outcome = run.get("outcome") or run.get("status")
    if outcome in ("success", "edited", "ok", "done"):
        return True
    if outcome in ("failed", "error"):
        return False
    if "ok" in run:
        return bool(run["ok"])
    return None


def assess(runs: list[dict], baseline_rate: float | None) -> dict | None:
    """runs newest first. Returns the drift reason, or None."""
    results = [r for r in (run_ok(x) for x in runs[:WINDOW]) if r is not None]
    if len(results) >= FAIL_STREAK and not any(results[:FAIL_STREAK]):
        return {"kind": "fail_streak", "because": f"last {FAIL_STREAK} runs failed", "window": len(results),
                "success_rate": round(sum(results) / len(results), 2)}
    if len(results) >= MIN_RUNS_FOR_RATE and baseline_rate is not None:
        rate = sum(results) / len(results)
        if rate < baseline_rate - RATE_DROP:
            return {"kind": "rate_drop", "window": len(results), "success_rate": round(rate, 2),
                    "because": f"success rate {rate:.0%} over last {len(results)} runs vs baseline "
                               f"{baseline_rate:.0%}"}
    return None


async def check_drift(tool_id: str) -> bool:
    db = deps.get_db()
    tool = await db.tools.find_one({"_id": tool_id})
    if not tool or tool.get("status") == "deprecated":
        return False
    runs = [r async for r in db.runs.find({"tool_id": tool_id}).sort("started_at", -1).limit(WINDOW)]
    baseline = (tool.get("baseline") or {}).get("success_rate")
    drift = assess(runs, baseline)
    if drift is None:
        if (tool.get("drift") or {}).get("active"):
            await db.tools.update_one({"_id": tool_id}, {"$set": {"drift.active": False}})
        return False

    open_heal = await db.jobs.find_one({"type": "heal", "payload.tool_id": tool_id,
                                        "status": {"$in": ["queued", "running"]}})
    if open_heal:
        return True
    now = datetime.now(UTC)
    failing = [r.get("_id") for r in runs if run_ok(r) is False][:FAIL_STREAK]
    job_id = await deps.enqueue_job("heal", {"tool_id": tool_id, "user_id": tool["user_id"],
                                             "detected_at": now.isoformat(), "failing_run_ids": failing,
                                             "drift": drift})
    await db.tools.update_one({"_id": tool_id}, {"$set": {"drift": {**drift, "active": True, "detected_at": now,
                                                                   "heal_job_id": job_id}}})
    await deps.publish(tool["user_id"], "drift_detected", {"tool_id": tool_id, "name": tool.get("name"),
                                                           "job_id": job_id, **drift})
    return True
