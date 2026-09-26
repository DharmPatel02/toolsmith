"""Phase 0 fixture stub. P1 owns its real implementation."""

from app.contracts import ToolDep
from app.fixtures import require_demo_user


async def resolve_deps(user_id: str, tool_id: str) -> list[ToolDep]:
    require_demo_user(user_id)
    return []


async def dependents(user_id: str, tool_id: str) -> list[str]:
    require_demo_user(user_id)
    return []
