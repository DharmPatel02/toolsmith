"""P2 trust endpoints: POST /prune (the demo's "Run prune" button)."""
from __future__ import annotations

import os

from fastapi import APIRouter

from app.forge import deps
from app.trust.prune import prune

router = APIRouter(tags=["p2-trust"])


@router.post("/prune")
async def post_prune(user_id: str | None = None, wait: bool = True) -> dict:
    """Runs a prune pass now (default) and returns {pruned, kept, toolbox_count};
    `?wait=false` queues a `prune` job for the worker and returns {job_id}."""
    uid = user_id or os.getenv("DEMO_USER_ID", "u_1")
    if not wait:
        return {"job_id": await deps.enqueue_job("prune", {"user_id": uid})}
    return await prune(uid)
