"""P2's handles on P1 services (db, events, search), in one place.

P2 modules import `get_db`, `publish` and `search_tools` from here, never from P1 modules
directly, so tests can swap them (`use_db`, `use_publisher`) and P2 still runs before
P1's code is merged.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger(__name__)

_db: Any = None
_publisher: Callable[[str, str, dict], Awaitable[None]] | None = None


def use_db(db: Any) -> None:
    global _db
    _db = db


def use_publisher(fn: Callable[[str, str, dict], Awaitable[None]] | None) -> None:
    global _publisher
    _publisher = fn


def get_db() -> Any:
    """The Mongo database (motor / pymongo-async API). P1's `app.db.get_db()` when present."""
    global _db
    if _db is None:
        try:
            from app.db import get_db as p1_get_db  # P1

            _db = p1_get_db()
        except ImportError:
            from motor.motor_asyncio import AsyncIOMotorClient

            _db = AsyncIOMotorClient(os.environ["MONGODB_URI"])[os.getenv("DB_NAME", "toolsmith")]
    return _db


async def publish(user_id: str, type: str, data: dict) -> None:
    if _publisher is not None:
        return await _publisher(user_id, type, data)
    try:
        from app.events import publish as p1_publish  # P1
    except ImportError:
        log.info("event %s %s", type, data)
        return
    await p1_publish(user_id, type, data)


async def search_tools(user_id: str, query: str, k: int = 5) -> list:
    try:
        from app.search import search_tools as p1_search  # P1
    except ImportError:
        return []
    return await p1_search(user_id, query, k)
