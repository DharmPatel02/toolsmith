"""P3: POST /ideas -> IdeaAnalysis (+ idea_id, candidate_id when confirmed). P4.2.4."""

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import llm
from app.concierge.ideas import analyze_idea

router = APIRouter(tags=["p3-ideas"])


class IdeaBody(BaseModel):
    text: str = ""
    confirm: bool = False
    idea_id: str | None = None
    user_id: str | None = None


@router.post("/ideas")
async def post_idea(body: IdeaBody) -> dict:
    if not body.text.strip() and not body.idea_id:
        raise HTTPException(422, "describe the idea in `text`")
    user_id = body.user_id or os.getenv("DEMO_USER_ID", "u_1")
    try:
        return await analyze_idea(user_id, body.text, confirm=body.confirm, idea_id=body.idea_id)
    except llm.LLMError as e:
        raise HTTPException(503, f"model unavailable: {e}") from e
