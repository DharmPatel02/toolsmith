"""Restored Phase 0 capture and lineage interfaces. All responses are fixtures."""

from fastapi import APIRouter, Query

from app.capture.state import paused_users
from app.config import get_settings
from app.contracts import CaptureSession, CaptureState, LineageResponse
from app.events import publish
from app.fixtures import fixture, require_demo_user

router = APIRouter()


def user():
    user_id = get_settings().demo_user_id
    require_demo_user(user_id)
    return user_id


@router.get("/capture/state", response_model=CaptureState)
async def state():
    return CaptureState(
        paused=user() in paused_users, allowed_origins=sorted(get_settings().allowed_origins)
    )


@router.post("/capture/pause")
async def pause():
    user_id = user()
    paused_users.add(user_id)
    await publish(user_id, "capture_paused", {"paused": True})
    return {"ok": True}


@router.post("/capture/resume")
async def resume():
    user_id = user()
    paused_users.discard(user_id)
    await publish(user_id, "capture_paused", {"paused": False})
    return {"ok": True}


@router.get("/capture/sessions", response_model=list[CaptureSession])
async def sessions():
    user()
    return []


@router.post("/capture/delete_last")
async def delete_last(minutes: int = Query(default=5, ge=1, le=60)):
    user()
    return {"deleted_frames": 0, "deleted_events": 0}


@router.get("/tools/{tool_id}/lineage", response_model=LineageResponse)
async def lineage(tool_id: str):
    user()
    if tool_id == "tool_uc2":
        return fixture("lineage_uc2.json")
    if tool_id == "tool_uc1":
        return {"calls": [], "merged_from": [], "merged_into": None, "dependents": []}
    raise LookupError("Unknown fixture tool")
