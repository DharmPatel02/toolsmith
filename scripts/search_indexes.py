"""Print index plans offline; --apply creates missing indexes and waits for READY.

Official schema: https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/
The index budget must be confirmed against the Atlas project, not guessed here.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pymongo.operations import SearchIndexModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import close_client, get_db  # noqa: E402


def index_plan(text_dims=1024, frame_dims=None):
    if not 1 <= text_dims <= 8192 or (frame_dims is not None and not 1 <= frame_dims <= 8192):
        raise ValueError("Embedding dimensions must be between 1 and 8192")

    def vector(collection, name, path, dimensions, status=False):
        fields = [
            {"type": "vector", "path": path, "numDimensions": dimensions, "similarity": "cosine"},
            {"type": "filter", "path": "user_id"},
        ]
        if status:
            fields.append({"type": "filter", "path": "status"})
        return {
            "collection": collection,
            "name": name,
            "type": "vectorSearch",
            "definition": {"fields": fields},
        }

    plans = [
        vector("tools", "tools_vec", "embedding", text_dims, True),
        vector("sessions", "sessions_vec", "intent_embedding", text_dims),
        {
            "collection": "tools",
            "name": "tools_text",
            "type": "search",
            "definition": {
                "mappings": {
                    "dynamic": False,
                    "fields": {
                        "user_id": {"type": "token"},
                        "status": {"type": "token"},
                        **{
                            field: {"type": "string"}
                            for field in ("title", "name", "tutorial_md", "keywords")
                        },
                    },
                }
            },
        },
    ]
    plans.append(vector("frames", "frames_vec", "embedding", frame_dims))
    plans.append(vector("patterns", "patterns_vec", "intent_centroid", text_dims, True))
    return plans


async def apply_indexes(db, plans, budget, *, timeout=180):
    if not 0 <= budget <= len(plans):
        raise ValueError("Budget must be 0–5")
    report = []
    for index, plan in enumerate(plans):
        if index >= budget:
            report.append(
                {"name": plan["name"], "status": "SKIPPED", "reason": "Configured index budget"}
            )
            continue
        if (
            plan["name"] == "frames_vec"
            and plan["definition"]["fields"][0]["numDimensions"] is None
        ):
            report.append(
                {
                    "name": plan["name"],
                    "status": "SKIPPED",
                    "reason": "Confirm multimodal dimension first",
                }
            )
            continue
        collection = db[plan["collection"]]
        rows = await (await collection.list_search_indexes(plan["name"])).to_list(length=None)
        if rows and rows[0].get("latestDefinition") != plan["definition"]:
            raise ValueError(
                f"Existing {plan['name']} definition differs; review it before changing"
            )
        if not rows:
            await collection.create_search_index(
                SearchIndexModel(
                    name=plan["name"], type=plan["type"], definition=plan["definition"]
                )
            )
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            rows = await (await collection.list_search_indexes(plan["name"])).to_list(length=None)
            if rows and rows[0].get("status") == "READY":
                report.append({"name": plan["name"], "status": "READY"})
                break
            if rows and rows[0].get("status") == "FAILED":
                raise RuntimeError(f"Index {plan['name']} failed to build")
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"Index {plan['name']} not READY after {timeout}s")
            await asyncio.sleep(2)
    return report


async def main(args):
    plans = index_plan(args.text_dims, args.frame_dims)
    try:
        result = await apply_indexes(get_db(), plans, args.budget) if args.apply else plans
        print(json.dumps(result, indent=2))
    finally:
        await close_client()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-dims", type=int, default=1024)
    parser.add_argument("--frame-dims", type=int)
    parser.add_argument("--budget", type=int, default=3)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args()))
