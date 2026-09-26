"""POST /candidates/{id}/approve | reject."""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.trust.promote import PromoteError, promote, reject

router = APIRouter(tags=["p2-candidates"])


class DecisionBody(BaseModel):
    user_id: str | None = None
    reason: str | None = None


def _user(body: DecisionBody | None) -> str:
    return (body and body.user_id) or os.getenv("DEMO_USER_ID", "u_1")


@router.post("/candidates/{candidate_id}/approve")
async def approve_candidate(candidate_id: str, body: DecisionBody | None = None) -> dict:
    try:
        return {"tool_id": await promote(candidate_id, _user(body))}
    except PromoteError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/candidates/{candidate_id}/reject")
async def reject_candidate(candidate_id: str, body: DecisionBody | None = None) -> dict:
    try:
        await reject(candidate_id, _user(body), body.reason if body else None)
    except PromoteError as e:
        raise HTTPException(409, str(e)) from e
    return {"ok": True}
