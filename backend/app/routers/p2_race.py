"""P2 race endpoints: POST /race (starts both sides, streams race_step), GET /race/{id}."""
from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.baseline.service import run_race, start_race
from app.forge import deps

router = APIRouter(tags=["p2-race"])
_background: set[asyncio.Task] = set()


class RaceBody(BaseModel):
    intent: str
    inputs: dict = Field(default_factory=dict)
    user_id: str | None = None


@router.post("/race")
async def post_race(body: RaceBody, wait: bool = False) -> dict:
    """Returns {race_id} at once; both sides stream `race_step` over SSE. `?wait=true` returns the result."""
    user_id = body.user_id or os.getenv("DEMO_USER_ID", "u_1")
    race_id = await start_race(user_id, body.intent, body.inputs)
    if wait:
        return await run_race(user_id, body.intent, body.inputs, race_id)
    task = asyncio.create_task(run_race(user_id, body.intent, body.inputs, race_id))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return {"race_id": race_id}


@router.get("/race/{race_id}")
async def get_race(race_id: str) -> dict:
    race = await deps.get_db().races.find_one({"_id": race_id})
    if not race:
        raise HTTPException(404, f"race {race_id} not found")
    return race
