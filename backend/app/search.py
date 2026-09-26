from app.contracts import EpisodeHit, ToolHit
from app.fixtures import fixture, require_demo_user


async def search_tools(user_id: str, query: str, k: int = 5) -> list[ToolHit]:
    require_demo_user(user_id)
    tool = fixture("tool_uc1.json")
    return [ToolHit(tool_id=tool["tool_id"], name=tool["name"], score=1)][: max(0, k)]


async def recall_episodes(user_id: str, query: str, k: int = 5) -> list[EpisodeHit]:
    require_demo_user(user_id)
    return [EpisodeHit(**item) for item in fixture("why_uc1.json")["episodes"]][: max(0, k)]
