"""Phase 0 fixture stub. P2 owns its real implementation."""

from app.contracts import Observation
from app.fixtures import require_demo_user


async def interpret_session(user_id: str, session_id: str) -> list[Observation]:
    require_demo_user(user_id)
    return []
