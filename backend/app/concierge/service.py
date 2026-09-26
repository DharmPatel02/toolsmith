"""Phase 0 fixture stub. P2 owns its real implementation."""

from app.contracts import ChatReply, IdeaAnalysis
from app.fixtures import require_demo_user


async def chat(user_id: str, conversation_id: str | None, message: str) -> ChatReply:
    require_demo_user(user_id)
    return ChatReply(
        conversation_id=conversation_id or "conversation_fixture",
        reply="Phase 0 fixture; concierge pending P2",
        tool_calls=[],
        cards=[],
    )


async def analyze_idea(user_id: str, text: str) -> IdeaAnalysis:
    require_demo_user(user_id)
    return IdeaAnalysis(
        covered_by_tool_id=None,
        feasible=False,
        scopes=[],
        deps=[],
        est_minutes_saved_week=0,
        spec=None,
    )
