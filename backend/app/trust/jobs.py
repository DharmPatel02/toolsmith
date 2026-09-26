"""Worker job `heal` (P2.3.2). Queued by check_drift with {tool_id, user_id, detected_at, failing_run_ids}."""
from __future__ import annotations

from app.trust.heal import heal_tool


async def handle_heal(job: dict) -> dict:
    p = job.get("payload", job)
    return await heal_tool(p["tool_id"], detected_at=p.get("detected_at"), failing_run_ids=p.get("failing_run_ids"))


JOBS = {"heal": handle_heal}


def register(register_fn) -> None:
    for job_type, handler in JOBS.items():
        register_fn(job_type, handler)
