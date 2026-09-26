"""Async MongoDB connection and explicit schema initialization (no startup writes)."""

import json
from datetime import datetime

from gridfs import AsyncGridFSBucket
from pymongo import ASCENDING, DESCENDING, AsyncMongoClient

from app.config import OBS_TTL_DAYS, ROOT, get_settings

_client = None


def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.mongodb_uri:
            raise RuntimeError("Set MONGODB_URI in .env before accessing Atlas")
        _client = AsyncMongoClient(
            settings.mongodb_uri, serverSelectionTimeoutMS=5000, tz_aware=True
        )
    return _client


def get_db():
    return get_client()[get_settings().db_name]


def get_gridfs() -> AsyncGridFSBucket:
    return AsyncGridFSBucket(get_db(), bucket_name="keyframes")


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def initialize_database(db) -> None:
    """Create collection types and indexes without deleting existing data."""
    names = set(await db.list_collection_names())
    if "observations" not in names:
        await db.create_collection(
            "observations",
            timeseries={"timeField": "ts", "metaField": "meta", "granularity": "seconds"},
            expireAfterSeconds=OBS_TTL_DAYS * 86400,
        )
    for name in (
        "sessions",
        "patterns",
        "tools",
        "tool_versions",
        "candidates",
        "runs",
        "verdicts",
        "feedback",
        "policy",
        "profile",
        "working_memory",
        "conversations",
        "jobs",
        "events",
        "frames",
        "ui_events",
        "action_vocab",
        "capture_sessions",
        "capture_state",
        "suggestion_impressions",
        "keyframes.files",
        "keyframes.chunks",
    ):
        if name not in names:
            await db.create_collection(name)

    for name in ("frames", "working_memory"):
        await db[name].create_index("expires_at", expireAfterSeconds=0)
    await db.patterns.create_index(
        [("user_id", ASCENDING), ("status", ASCENDING), ("value", DESCENDING)]
    )
    await db.tools.create_index([("user_id", ASCENDING), ("name", ASCENDING)], unique=True)
    await db.tools.create_index("lineage.calls")
    await db.runs.create_index([("tool_id", ASCENDING), ("started_at", DESCENDING)])
    await db.frames.create_index(
        [("user_id", ASCENDING), ("session_id", ASCENDING), ("ts", ASCENDING)]
    )
    await db.ui_events.create_index([("user_id", ASCENDING), ("ts", DESCENDING)])
    await db.ui_events.create_index("url_template")
    await db["keyframes.files"].create_index([("filename", ASCENDING), ("uploadDate", ASCENDING)])
    await db["keyframes.chunks"].create_index(
        [("files_id", ASCENDING), ("n", ASCENDING)], unique=True
    )
    for item in json.loads((ROOT / "data/action_vocab_seed.json").read_text()):
        item["first_seen"] = datetime.fromisoformat(item["first_seen"].replace("Z", "+00:00"))
        await db.action_vocab.update_one({"_id": item["_id"]}, {"$setOnInsert": item}, upsert=True)
