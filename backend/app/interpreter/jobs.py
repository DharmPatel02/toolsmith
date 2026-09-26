"""Worker job `interpret` (P2.2.6): label a session's frames, then hand the T2 steps to
P1's fusion. P1's worker queues one debounced job per session."""
from __future__ import annotations

import logging

from app.interpreter.service import interpret_session_detailed

log = logging.getLogger(__name__)


async def handle_interpret(job: dict) -> dict:
    p = job.get("payload", job)
    observations, stats = await interpret_session_detailed(p["user_id"], p["session_id"])
    fused = None
    try:
        # P1: structured steps win, frames become evidence
        from app.capture.service import fuse
    except ImportError:
        log.warning("fusion not available yet; %d T2 steps left on frames", len(observations))
    else:
        fused = await fuse(p["user_id"], p["session_id"])
    return {**stats, "observations": len(observations), "fused": fused}


JOBS = {"interpret": handle_interpret}


def register(register_fn) -> None:
    for job_type, handler in JOBS.items():
        register_fn(job_type, handler)
