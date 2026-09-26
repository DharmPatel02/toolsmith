"""Verify live Atlas hybrid ranking with temporary, isolated tool documents."""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import search  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import close_client, get_db  # noqa: E402


async def main():
    settings = get_settings()
    original_stub_mode = settings.stub_mode
    original_embed = search.embed
    user_id = "verify_search_" + uuid4().hex
    target_id = "verify_target_" + uuid4().hex
    docs = [
        {
            "_id": target_id,
            "tool_id": target_id,
            "user_id": user_id,
            "status": "active",
            "name": "weekly_revenue_rollup",
            "title": "Weekly revenue rollup",
            "tutorial_md": "Produce a weekly revenue summary grouped by region.",
            "keywords": ["weekly", "revenue", "region"],
            "embedding": [1.0] + [0.0] * 1023,
        },
        {
            "_id": "verify_inventory_" + uuid4().hex,
            "tool_id": "verify_inventory",
            "user_id": user_id,
            "status": "active",
            "name": "inventory_review",
            "title": "Inventory review",
            "tutorial_md": "Review stock levels and supplier delays.",
            "keywords": ["inventory", "stock"],
            "embedding": [0.0, 1.0] + [0.0] * 1022,
        },
        {
            "_id": "verify_hiring_" + uuid4().hex,
            "tool_id": "verify_hiring",
            "user_id": user_id,
            "status": "active",
            "name": "hiring_plan",
            "title": "Quarterly hiring plan",
            "tutorial_md": "Summarize candidate pipeline and staffing needs.",
            "keywords": ["quarterly", "hiring"],
            "embedding": [0.0, 0.0, 1.0] + [0.0] * 1021,
        },
    ]

    async def query_embedding(_texts, input_type="query"):
        return [[1.0] + [0.0] * 1023]

    db = get_db()
    try:
        settings.stub_mode = False
        search.embed = query_embedding
        await db.tools.insert_many(docs)
        hits = []
        for _ in range(20):
            hits = await search.search_tools(user_id, "summarize the weekly revenue by region", k=3)
            if hits and hits[0].tool_id == target_id:
                break
            await asyncio.sleep(1)
        if not hits or hits[0].tool_id != target_id:
            print("Observed ranking:", [(hit.name, round(hit.score, 4)) for hit in hits])
            raise RuntimeError("Hybrid ranking did not place the matching tool first")
        print("OK: hybrid search ranked the matching tool first")
    finally:
        await db.tools.delete_many({"user_id": user_id})
        settings.stub_mode = original_stub_mode
        search.embed = original_embed
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())
