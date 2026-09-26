"""Phase 0 fixture stub. P2 owns its real implementation."""

from app.contracts import Run
from app.fixtures import fixture, require_demo_user, require_stub


async def promote(candidate_id: str, user_id: str) -> str:
    require_demo_user(user_id)
    if candidate_id != fixture("candidate_uc1.json")["_id"]:
        raise LookupError("Unknown fixture candidate")
    return fixture("tool_uc1.json")["tool_id"]


async def update_after_run(run: Run) -> None:
    require_demo_user(run.user_id)


async def check_drift(tool_id: str) -> bool:
    require_stub()
    return False
