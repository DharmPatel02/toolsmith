"""Capture controls and tool lineage routes."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from app.capture.state import is_paused, set_paused
from app.config import get_settings
from app.contracts import CaptureSession, CaptureState, LineageResponse
from app.db import get_db, get_gridfs
from app.events import publish
from app.fixtures import require_demo_user
from app.runtime.lineage import lineage as lineage_for_tool

router = APIRouter()


def user():
    user_id = get_settings().demo_user_id
    if get_settings().stub_mode:
        require_demo_user(user_id)
    return user_id


@router.get("/capture/state", response_model=CaptureState)
async def state():
    return CaptureState(
        paused=await is_paused(user()), allowed_origins=sorted(get_settings().allowed_origins)
    )


@router.post("/capture/pause")
async def pause():
    user_id = user()
    await set_paused(user_id, True)
    await publish(user_id, "capture_paused", {"paused": True})
    return {"ok": True}


@router.post("/capture/resume")
async def resume():
    user_id = user()
    await set_paused(user_id, False)
    await publish(user_id, "capture_paused", {"paused": False})
    return {"ok": True}


@router.get("/capture/sessions", response_model=list[CaptureSession])
async def sessions():
    user_id = user()
    if get_settings().stub_mode:
        return []
    rows = (
        await get_db()
        .capture_sessions.find({"user_id": user_id})
        .sort("started_at", -1)
        .to_list(length=100)
    )
    fields = CaptureSession.model_fields
    return [{key: row[key] for key in fields if key in row} for row in rows]


@router.post("/capture/delete_last")
async def delete_last(minutes: int = Query(default=5, ge=1, le=60)):
    user_id = user()
    if get_settings().stub_mode:
        return {"deleted_frames": 0, "deleted_events": 0}
    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    frames = await db.frames.find(
        {"user_id": user_id, "ts": {"$gte": cutoff}}, {"_id": 1, "gridfs_id": 1}
    ).to_list(length=None)
    frame_ids = [item["_id"] for item in frames]
    for item in frames:
        if item.get("gridfs_id"):
            try:
                await get_gridfs().delete(item["gridfs_id"])
            except Exception:
                pass
    frame_result = (
        await db.frames.delete_many({"user_id": user_id, "_id": {"$in": frame_ids}})
        if frame_ids
        else None
    )
    event_result = await db.ui_events.delete_many({"user_id": user_id, "ts": {"$gte": cutoff}})
    await db.observations.delete_many({"meta.user_id": user_id, "ts": {"$gte": cutoff}})
    return {
        "deleted_frames": frame_result.deleted_count if frame_result else 0,
        "deleted_events": event_result.deleted_count,
    }


@router.get("/tools/{tool_id}/lineage", response_model=LineageResponse)
async def lineage(tool_id: str):
    return await lineage_for_tool(user(), tool_id)
