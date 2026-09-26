"""P2 concierge endpoint: POST /chat -> ChatReply{conversation_id, reply, tool_calls, cards}."""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import llm
from app.concierge.service import chat

router = APIRouter(tags=["p2-chat"])


class ChatBody(BaseModel):
    message: str
    conversation_id: str | None = None
    user_id: str | None = None


@router.post("/chat")
async def post_chat(body: ChatBody) -> dict:
    try:
        return await chat(body.user_id or os.getenv("DEMO_USER_ID", "u_1"), body.conversation_id, body.message)
    except llm.LLMError as e:
        raise HTTPException(503, f"model unavailable: {e}") from e
