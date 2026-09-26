"""Process-local Phase 0 event feed. Atlas-backed SSE belongs to P1.2.5."""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from app.config import get_settings
from app.contracts import Event
from app.db import get_db
from app.fixtures import require_demo_user

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


async def publish(user_id: str, type: str, data: dict) -> None:
    event = Event(type=type, ts=datetime.now(timezone.utc), data=data)
    if not get_settings().stub_mode:
        if not user_id:
            raise ValueError("user_id is required")
        await get_db().events.insert_one(
            {"user_id": user_id, **event.model_dump()}
        )
        return
    require_demo_user(user_id)
    for queue in tuple(_subscribers[user_id]):
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(event)


async def subscribe(user_id: str):
    if not get_settings().stub_mode:
        if not user_id:
            raise ValueError("user_id is required")
        async for chunk in _subscribe_atlas(user_id):
            yield chunk
        return
    require_demo_user(user_id)
    queue = asyncio.Queue(maxsize=100)
    _subscribers[user_id].add(queue)
    try:
        yield ": Phase 0 fixture stream; process-local events only\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                yield f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"
            except TimeoutError:
                yield ": heartbeat\n\n"
    finally:
        _subscribers[user_id].discard(queue)
        if not _subscribers[user_id]:
            del _subscribers[user_id]


async def _subscribe_atlas(user_id: str):
    resume_token = None
    while True:
        stream = None
        next_change = None
        try:
            options = {}
            if resume_token is not None:
                options["resume_after"] = resume_token
            stream = await get_db().events.watch(
                [
                    {
                        "$match": {
                            "operationType": "insert",
                            "fullDocument.user_id": user_id,
                        }
                    }
                ],
                **options,
            )
            async with stream:
                yield ": connected\n\n"
                next_change = asyncio.create_task(anext(stream))
                while True:
                    try:
                        change = await asyncio.wait_for(
                            asyncio.shield(next_change), timeout=15
                        )
                    except TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    resume_token = stream.resume_token
                    document = change.get("fullDocument") or {}
                    event = Event(
                        type=document["type"], ts=document["ts"], data=document.get("data", {})
                    )
                    yield f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"
                    next_change = asyncio.create_task(anext(stream))
        except asyncio.CancelledError:
            raise
        except Exception:
            yield ": reconnecting\n\n"
            await asyncio.sleep(1)
        finally:
            if next_change is not None:
                if not next_change.done():
                    next_change.cancel()
                await asyncio.gather(next_change, return_exceptions=True)
