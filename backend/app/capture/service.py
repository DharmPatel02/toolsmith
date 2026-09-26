"""Capture validation, Atlas persistence, and structured/frame fusion."""

import base64
import binascii
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

from app.capture.state import is_paused
from app.config import (
    FRAMES_TTL_DAYS,
    FUSION_WINDOW_S,
    MAX_FRAMES_PER_SEC,
    MAX_FRAMES_PER_SESSION,
    get_settings,
)
from app.contracts import (
    CaptureAck,
    CaptureBatch,
    Evidence,
    Observation,
    ObservationBatch,
    ObservationMeta,
)
from app.db import get_db, get_gridfs
from app.fixtures import require_demo_user


def validate_batch(batch: CaptureBatch) -> None:
    if batch.source == "desktop":
        raise PermissionError("Desktop capture is outside the three-person demo scope")
    for item in [*batch.events, *batch.frames]:
        parsed = urlsplit(item.url_template)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in get_settings().allowed_origins:
            raise PermissionError("Capture origin is not allow-listed")
    if batch.source == "video_replay" and batch.events:
        raise ValueError("Video replay batches contain frames only")
    for frame in batch.frames:
        try:
            raw = base64.b64decode(frame.image_webp_b64, validate=True)
            with Image.open(BytesIO(raw)) as image:
                if image.format != "WEBP":
                    raise ValueError("Frame must contain a WebP image")
                image.verify()
        except (binascii.Error, UnidentifiedImageError, OSError) as exc:
            raise ValueError("Invalid base64 WebP frame") from exc


def _event_id(user_id: str, session_id: str, event) -> str:
    key = f"{user_id}:{session_id}:{event.model_dump_json()}"
    return "ue_" + sha256(key.encode()).hexdigest()[:24]


def _observation(user_id: str, session_id: str, event, frame_ids: list[str]) -> Observation:
    action = {"click": "web.click", "submit": "web.submit", "nav": "web.navigate"}[event.kind]
    target = event.element.model_dump(exclude_defaults=True)
    shape = event.value_shape.model_dump() if event.value_shape else {}
    return Observation(
        ts=event.ts,
        meta=ObservationMeta(user_id=user_id, source="chrome"),
        session_id=session_id,
        action=action,
        signature=action,
        target=target,
        args_shape=shape,
        evidence=Evidence(frame_ids=frame_ids, tier="T1"),
    )


async def _store_live_batch(user_id: str, batch: CaptureBatch) -> CaptureAck:
    db = get_db()
    now = datetime.now(timezone.utc)
    audit_id = f"{user_id}:{batch.capture_session_id}"
    audit = await db.capture_sessions.find_one({"_id": audit_id, "user_id": user_id})
    if await is_paused(user_id) or (audit and audit.get("paused")):
        return CaptureAck(ui_events=0, frames_kept=0, frames_dropped=len(batch.frames), paused=True)
    if not audit:
        audit = {
            "_id": audit_id,
            "user_id": user_id,
            "capture_session_id": batch.capture_session_id,
            "started_at": now,
            "ended_at": None,
            "sources": [],
            "apps_seen": [],
            "frames_kept": 0,
            "frames_dropped_by_rule": {},
            "paused": False,
        }
    room = max(0, MAX_FRAMES_PER_SESSION - audit["frames_kept"])
    frames = []
    dropped = 0
    for frame in sorted(batch.frames, key=lambda item: item.ts):
        window = timedelta(seconds=1 / MAX_FRAMES_PER_SEC)
        existing_in_window = await db.frames.find_one(
            {
                "user_id": user_id,
                "capture_session_id": batch.capture_session_id,
                "ts": {"$gte": frame.ts - window, "$lte": frame.ts + window},
            },
            {"_id": 1},
        )
        if (
            len(frames) >= room
            or existing_in_window
            or any(
                abs((frame.ts - kept.ts).total_seconds()) < 1 / MAX_FRAMES_PER_SEC
                for kept in frames
            )
        ):
            dropped += 1
            continue
        frames.append(frame)
    gridfs = get_gridfs()
    frame_ids: dict[str, str] = {}
    new_frame_count = 0
    event_docs = []
    observations = []

    for item in batch.events:
        event_id = _event_id(user_id, batch.capture_session_id, item)
        doc = item.model_dump()
        doc.update(
            {"_id": event_id, "user_id": user_id, "capture_session_id": batch.capture_session_id}
        )
        event_docs.append(doc)

    for frame in frames:
        frame_id = (
            "fr_"
            + sha256(
                f"{user_id}:{batch.capture_session_id}:{frame.client_id}".encode()
            ).hexdigest()[:24]
        )
        frame_ids[frame.client_id] = frame_id
        if await db.frames.find_one({"_id": frame_id, "user_id": user_id}, {"_id": 1}):
            continue
        raw = base64.b64decode(frame.image_webp_b64, validate=True)
        thumb_buffer = BytesIO()
        with Image.open(BytesIO(raw)) as image:
            image.thumbnail((256, 256))
            image.save(thumb_buffer, format="WEBP")
        gridfs_id = await gridfs.upload_from_stream(frame_id, raw, metadata={"user_id": user_id})
        nearest = min(
            batch.events, key=lambda e: abs((e.ts - frame.ts).total_seconds()), default=None
        )
        session_id = (
            nearest.session_id if nearest and nearest.session_id else batch.capture_session_id
        )
        await db.frames.insert_one(
            {
                "_id": frame_id,
                "user_id": user_id,
                "session_id": session_id,
                "capture_session_id": batch.capture_session_id,
                "ts": frame.ts,
                "source": batch.source,
                "app": frame.app,
                "window_title": frame.window_title,
                "url_template": frame.url_template,
                "trigger": frame.trigger,
                "gridfs_id": gridfs_id,
                "thumb": thumb_buffer.getvalue(),
                "label": None,
                "expires_at": now + timedelta(days=FRAMES_TTL_DAYS),
                "created_at": now,
            }
        )
        new_frame_count += 1

    for event in batch.events:
        matched = []
        for frame in batch.frames:
            if frame.client_id not in frame_ids:
                continue
            if abs((event.ts - frame.ts).total_seconds()) <= FUSION_WINDOW_S:
                matched.append(frame_ids[frame.client_id])
        observations.append(
            _observation(user_id, event.session_id or batch.capture_session_id, event, matched)
        )

    inserted_events = 0
    if event_docs:
        for document in event_docs:
            result = await db.ui_events.update_one(
                {"_id": document["_id"]}, {"$setOnInsert": document}, upsert=True
            )
            inserted_events += int(result.upserted_id is not None)
    if observations:
        for observation in observations:
            key = ":".join(
                (
                    "capture",
                    observation.session_id or "",
                    observation.ts.isoformat(),
                    observation.action,
                )
            )
            exists = await db.observations.find_one(
                {"meta.user_id": user_id, "capture_key": key}, {"_id": 1}
            )
            if not exists:
                document = observation.model_dump()
                document["capture_key"] = key
                await db.observations.insert_one(document)
        from app.ingest.service import ingest

        await ingest(ObservationBatch(user_id=user_id, events=[]))

    apps = sorted(set(audit["apps_seen"]) | {frame.app for frame in frames})
    sources = sorted(set(audit["sources"]) | {batch.source})
    await db.capture_sessions.replace_one(
        {"_id": audit_id, "user_id": user_id},
        {
            **audit,
            "apps_seen": apps,
            "sources": sources,
            "frames_kept": audit["frames_kept"] + new_frame_count,
            "updated_at": now,
        },
        upsert=True,
    )
    return CaptureAck(
        ui_events=inserted_events,
        frames_kept=new_frame_count,
        frames_dropped=dropped,
        paused=False,
    )


async def ingest_capture_batch(user_id: str, batch: CaptureBatch) -> CaptureAck:
    if get_settings().stub_mode:
        require_demo_user(user_id)
    elif user_id != get_settings().demo_user_id:
        raise PermissionError("Capture is enabled only for the configured demo user")
    if batch.user_id != user_id:
        raise PermissionError("Capture batch user does not match request user")
    validate_batch(batch)
    if get_settings().stub_mode:
        if await is_paused(user_id):
            return CaptureAck(
                ui_events=0, frames_kept=0, frames_dropped=len(batch.frames), paused=True
            )
        return CaptureAck(
            ui_events=len(batch.events),
            frames_kept=len(batch.frames),
            frames_dropped=0,
            paused=False,
        )
    return await _store_live_batch(user_id, batch)


async def fuse(user_id: str, session_id: str) -> int:
    """Attach labeled nearby frames to T1 observations; emit T2 only for unmatched labels."""
    if get_settings().stub_mode:
        require_demo_user(user_id)
        return 0
    db = get_db()
    frames = await db.frames.find(
        {
            "user_id": user_id,
            "session_id": session_id,
            "label": {"$ne": None},
            "fused": {"$ne": True},
        }
    ).to_list(length=None)
    count = 0
    for frame in frames:
        delta = FUSION_WINDOW_S * 1000
        nearby = await db.observations.find_one(
            {
                "meta.user_id": user_id,
                "session_id": session_id,
                "ts": {
                    "$gte": frame["ts"] - timedelta(milliseconds=delta),
                    "$lte": frame["ts"] + timedelta(milliseconds=delta),
                },
                "evidence.tier": {"$in": ["T0", "T1"]},
            }
        )
        if nearby:
            pass
        else:
            label = frame["label"]
            if label.get("needs_review"):
                await db.frames.update_one(
                    {"_id": frame["_id"], "user_id": user_id}, {"$set": {"fused": True}}
                )
                continue
            action = label["verb"]
            key = f"frame:{frame['_id']}"
            exists = await db.observations.find_one(
                {"meta.user_id": user_id, "capture_key": key}, {"_id": 1}
            )
            if not exists:
                await db.observations.insert_one(
                    Observation(
                        ts=frame["ts"],
                        meta=ObservationMeta(
                            user_id=user_id,
                            source="video_replay"
                            if frame["source"] == "video_replay"
                            else "chrome",
                        ),
                        session_id=session_id,
                        action=action,
                        signature=action,
                        args_shape=label.get("args_shape", {}),
                        evidence=Evidence(
                            frame_ids=[frame["_id"]],
                            tier="T2",
                            confidence=label["confidence"],
                            needs_review=label.get("needs_review", False),
                        ),
                    ).model_dump()
                    | {"capture_key": key}
                )
        await db.frames.update_one(
            {"_id": frame["_id"], "user_id": user_id}, {"$set": {"fused": True}}
        )
        count += 1
    return count
