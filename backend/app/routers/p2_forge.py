"""P2 forge endpoints: POST /dev/forge, GET /candidates/{id}."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.forge import deps
from app.forge.service import forge_from_pattern_doc, new_candidate_id

log = logging.getLogger(__name__)
router = APIRouter(tags=["p2-forge"])
_background: set[asyncio.Task] = set()


class DevForgeBody(BaseModel):
    pattern: dict


@router.post("/dev/forge")
async def dev_forge(body: DevForgeBody, wait: bool = False) -> dict:
    """Dev-only (I-1b): forge a candidate from a pattern given inline. Returns at once and
    streams forge_started / forged over SSE; `?wait=true` blocks until the candidate exists."""
    pattern = body.pattern
    if "user_id" not in pattern:
        raise HTTPException(422, "pattern.user_id is required")
    cid = new_candidate_id()
    if wait:
        await forge_from_pattern_doc(pattern, cid)
    else:
        task = asyncio.create_task(forge_from_pattern_doc(pattern, cid))
        _background.add(task)
        task.add_done_callback(_background.discard)
    return {"candidate_id": cid}


@router.get("/candidates/{candidate_id}")
async def get_candidate(candidate_id: str) -> dict:
    db = deps.get_db()
    cand = await db.candidates.find_one({"_id": candidate_id})
    if not cand:
        raise HTTPException(404, f"candidate {candidate_id} not found (still forging?)")
    cand["verdict"] = await db.verdicts.find_one({"_id": cand["verdict_id"]}) if cand.get("verdict_id") else None
    return cand
