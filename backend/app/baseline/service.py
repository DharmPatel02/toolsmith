"""Phase 0 fixture stub. P2 owns its real implementation."""

from app.contracts import BaselineResult
from app.fixtures import require_demo_user


async def run_baseline(user_id: str, intent: str, inputs: dict, race_id: str) -> BaselineResult:
    require_demo_user(user_id)
    return BaselineResult(
        race_id=race_id, output={"summary": "Phase 0 fixture"}, steps=0, seconds=0, tokens=0
    )
