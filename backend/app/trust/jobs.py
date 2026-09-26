"""Worker jobs `heal` (P2.3.2, queued by check_drift with {tool_id, user_id, detected_at,
failing_run_ids}) and `prune` (P2.3.3, payload {user_id})."""
from __future__ import annotations

import os

from app.trust.heal import heal_tool
from app.trust.prune import prune


async def handle_heal(job: dict) -> dict:
    p = job.get("payload", job)
    return await heal_tool(p["tool_id"], detected_at=p.get("detected_at"), failing_run_ids=p.get("failing_run_ids"))


async def handle_prune(job: dict) -> dict:
    p = job.get("payload", job) or {}
    return await prune(p.get("user_id") or os.getenv("DEMO_USER_ID", "u_1"))


JOBS = {"heal": handle_heal, "prune": handle_prune}


def register(register_fn) -> None:
    for job_type, handler in JOBS.items():
        register_fn(job_type, handler)
