"""Phase 0 fixture stub. P2 owns its real implementation."""

from app.contracts import ToolSpec
from app.fixtures import fixture, require_demo_user


async def forge_from_pattern(pattern_id: str) -> str:
    candidate = fixture("candidate_uc1.json")
    if candidate["pattern_id"] != pattern_id:
        raise LookupError("Unknown fixture pattern")
    return candidate["_id"]


async def forge_from_spec(user_id: str, spec: ToolSpec, origin: dict) -> str:
    require_demo_user(user_id)
    return fixture("candidate_uc1.json")["_id"]
