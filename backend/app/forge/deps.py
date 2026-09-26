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
        return await _local_search_tools(user_id, query, k)
    return await p1_search(user_id, query, k)


async def _local_search_tools(user_id: str, query: str, k: int) -> list[dict]:
    """Until P1's search lands: cosine over `tools.embedding` in Python (dev only, small N)."""
    from app import embeddings

    tools = [t async for t in get_db().tools.find({"user_id": user_id, "status": {"$ne": "deprecated"},
                                                   "embedding": {"$exists": True}},
                                                  {"name": 1, "embedding": 1})]
    if not tools or not query:
        return []
    q = (await embeddings.embed([query], "query"))[0]
    hits = [{"tool_id": t["_id"], "name": t.get("name"), "score": embeddings.cosine(q, t["embedding"])}
            for t in tools]
    return sorted(hits, key=lambda h: -h["score"])[:k]


class MissingDependency(LookupError):
    pass


async def dependency_code(user_id: str, names: list[str], max_depth: int = 4) -> dict[str, str]:
    """{tool_name: active version code} for a composed tool's `requires.tools`, transitively
    (a dep may call deps). Fails closed: a missing or inactive dependency raises."""
    db = get_db()
    out: dict[str, str] = {}
    frontier = list(dict.fromkeys(names))
    for _ in range(max_depth):
        if not frontier:
            break
        nxt = []
        for name in frontier:
            if name in out:
                continue
            tool = await db.tools.find_one({"user_id": user_id, "name": name, "status": "active"})
            if not tool:
                raise MissingDependency(f"dependency {name!r} is not an active tool")
            tv = await db.tool_versions.find_one({"_id": f"{tool['_id']}@v{tool['active_version']}"})
            if not tv:
                raise MissingDependency(f"dependency {name!r} has no active version")
            out[name] = tv["code"]
            nxt += (tv.get("requires") or {}).get("tools") or []
        frontier = nxt
    return out


async def dependents(user_id: str, tool_id: str) -> list[str]:
    """Active tools that call this one (prune safety). P1's lineage when present."""
    try:
        from app.runtime.lineage import dependents as p1_dependents  # P1
    except ImportError:
        pass
    else:
        return await p1_dependents(user_id, tool_id)
    return [t["_id"] async for t in get_db().tools.find(
        {"user_id": user_id, "status": "active", "lineage.calls": tool_id, "_id": {"$ne": tool_id}}, {"_id": 1})]


async def recall_episodes(user_id: str, query: str, k: int = 5) -> list:
    try:
        from app.search import recall_episodes as p1_recall  # P1
    except ImportError:
        return await _local_recall_episodes(user_id, query, k)
    return await p1_recall(user_id, query, k)


async def _local_recall_episodes(user_id: str, query: str, k: int) -> list[dict]:
    """Until P1's search lands: cosine over closed sessions' `intent_embedding` (EpisodeHit shape)."""
    from app import embeddings

    sessions = [s async for s in get_db().sessions.find({"user_id": user_id, "intent_embedding": {"$exists": True}})]
    if not sessions or not query:
        return []
    q = (await embeddings.embed([query], "query"))[0]
    hits = []
    for s in sessions:
        start = s.get("started_at") or s.get("start")
        hits.append({"session_id": s["_id"], "date": start.date().isoformat() if hasattr(start, "date") else start,
                     "intent_summary": s.get("intent_summary"), "minutes": s.get("minutes"),
                     "tokens": s.get("tokens"), "score": embeddings.cosine(q, s["intent_embedding"])})
    return sorted(hits, key=lambda h: -h["score"])[:k]


async def run_by_intent(user_id: str, intent: str, inputs: dict) -> Any:
    from app.runtime.service import run_by_intent as p1_run  # P1; no fallback, callers handle ImportError
    return await p1_run(user_id, intent, inputs)


async def run_tool(user_id: str, tool_id: str, params: dict, confirm: bool = False) -> Any:
    from app.runtime.service import run_tool as p1_run_tool  # P1
    return await p1_run_tool(user_id, tool_id, params, confirm)


async def record_change(user_id: str, field: str, new, direction: str, because: str,
                        origin_ids: list[str]) -> Any:
    """P1's policy change log. Fallback writes the same shape straight into `policy`."""
    try:
        from app.policy.service import record_change as p1_record  # P1
    except ImportError:
        pass
    else:
        return await p1_record(user_id, field, new, direction, because, origin_ids)
    import secrets
    from datetime import UTC, datetime

    change = {"_id": "chg_" + secrets.token_hex(4), "field": field, "new": new, "direction": direction,
              "because": because, "origin_ids": origin_ids, "status": "applied", "ts": datetime.now(UTC)}
    await get_db().policy.update_one({"_id": f"policy:{user_id}"},
                                     {"$set": {field: new}, "$push": {"changes": change},
                                      "$inc": {"version": 1}}, upsert=True)
    await publish(user_id, "policy_changed", {k: v for k, v in change.items() if k != "ts"})
    return change


async def enqueue_job(type: str, payload: dict) -> str:
    """Queue a job in `jobs` (§3.2); P1's worker dispatches it by change stream."""
    import secrets
    from datetime import UTC, datetime

    jid = "job_" + secrets.token_hex(4)
    await get_db().jobs.insert_one({"_id": jid, "type": type, "payload": payload, "status": "queued",
                                    "error": None, "created_at": datetime.now(UTC)})
    return jid


def field(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from a dict or a Pydantic/dataclass result (P1 returns models)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
