"""Post deterministic history to the API. Reset is scoped to a configured demo user."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import get_settings  # noqa: E402
from app.db import close_client, get_db, get_gridfs  # noqa: E402


def load_events(directory, user_id, logs_only=False):
    path = Path(directory) / ("history_logs_only.jsonl" if logs_only else "history.jsonl")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for row in rows:
        original = row["meta"]["user_id"]
        row["meta"]["user_id"] = user_id
        if original != user_id and row.get("session_id"):
            row["session_id"] = user_id + ":" + row["session_id"]
            row["evidence"]["frame_ids"] = [
                user_id + ":" + frame for frame in row["evidence"].get("frame_ids", [])
            ]
    return sorted(rows, key=lambda row: row["ts"])


async def reset_live_user(user_id):
    """Never drop databases or collections, and never clear a non-demo tenant."""
    demo = get_settings().demo_user_id
    if user_id not in (demo, demo + "_logs_only"):
        raise ValueError("Reset is limited to the configured demo and ablation users")
    db = get_db()
    tools = await db.tools.find({"user_id": user_id}, {"_id": 1}).to_list(length=None)
    frames = await db.frames.find({"user_id": user_id}, {"gridfs_id": 1}).to_list(length=None)
    for frame in frames:
        if frame.get("gridfs_id"):
            await get_gridfs().delete(frame["gridfs_id"])
    await db.tool_versions.delete_many({"tool_id": {"$in": [tool["_id"] for tool in tools]}})
    await db.observations.delete_many({"meta.user_id": user_id})
    for name in (
        "sessions",
        "patterns",
        "tools",
        "candidates",
        "runs",
        "verdicts",
        "feedback",
        "profile",
        "working_memory",
        "conversations",
        "events",
        "frames",
        "ui_events",
        "capture_sessions",
    ):
        await db[name].delete_many({"user_id": user_id})
    await db.jobs.delete_many({"payload.user_id": user_id})
    await db.policy.delete_one({"_id": f"policy:{user_id}"})


async def seed(client, events, user_id, batch_size=100):
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    inserted = 0
    for offset in range(0, len(events), batch_size):
        response = await client.post(
            "/observations/bulk",
            json={"user_id": user_id, "events": events[offset : offset + batch_size]},
        )
        response.raise_for_status()
        inserted += response.json()["inserted"]
    return {
        "inserted": inserted,
        "batches": (len(events) + batch_size - 1) // batch_size,
        "user_id": user_id,
    }


async def main(args):
    settings = get_settings()
    user_id = settings.demo_user_id + ("_logs_only" if args.logs_only else "")
    events = load_events(args.directory, user_id, args.logs_only)
    async with httpx.AsyncClient(base_url=args.api, timeout=120) as client:
        health = await client.get("/health")
        health.raise_for_status()
        if args.reset:
            if health.json()["mode"] == "fixture":
                response = await client.post("/dev/reset-history", json={"user_id": user_id})
                response.raise_for_status()
            else:
                if settings.stub_mode:
                    raise RuntimeError(
                        "API is live but local configuration is fixture mode; refusing reset"
                    )
                await reset_live_user(user_id)
        result = await seed(client, events, user_id, args.batch_size)
        result["mode"] = health.json()["mode"]
        print(json.dumps(result))
    await close_client()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="data/seed")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--logs-only", action="store_true")
    asyncio.run(main(parser.parse_args()))
