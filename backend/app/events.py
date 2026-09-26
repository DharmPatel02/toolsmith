"""Process-local Phase 0 event feed. Atlas-backed SSE belongs to P1.2.5."""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from app.contracts import Event
from app.fixtures import require_demo_user

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


async def publish(user_id: str, type: str, data: dict) -> None:
    require_demo_user(user_id)
    event = Event(type=type, ts=datetime.now(timezone.utc), data=data)
    for queue in tuple(_subscribers[user_id]):
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(event)


async def subscribe(user_id: str):
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
