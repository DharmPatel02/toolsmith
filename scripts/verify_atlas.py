"""Live checks for P1.1.2, with isolated probes removed after each test.

Requires configured Atlas credentials. Prints OK/FAIL/UNVERIFIED, never invented
success. Model availability/dimensions and tier quotas require provider/account
metadata and remain UNVERIFIED when that metadata is not supplied.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import close_client, get_db, get_gridfs  # noqa: E402


async def verify(args):
    db = get_db()
    report = []

    async def check(name, operation):
        try:
            detail = await operation()
            report.append({"check": name, "status": "OK", "detail": detail})
        except Exception as exc:
            # Do not print connection strings or credentials carried in exceptions.
            report.append({"check": name, "status": "FAIL", "detail": type(exc).__name__})

    async def version():
        result = await db.command("buildInfo")
        if tuple(result["versionArray"][:2]) < (8, 1):
            raise RuntimeError("Use client-side RRF on this server")
        return result["version"]

    async def stream(name):
        probe = "verify_" + uuid4().hex
        try:
            async with await db[name].watch(
                [{"$match": {"documentKey._id": probe}}], max_await_time_ms=500
            ) as changes:
                await db[name].insert_one({"_id": probe, "user_id": "__toolsmith_verification__"})
                change = await asyncio.wait_for(anext(changes), timeout=10)
                return change["operationType"]
        finally:
            await db[name].delete_one({"_id": probe})

    async def gridfs():
        bucket = get_gridfs()
        file_id = await bucket.upload_from_stream(
            "verify-" + uuid4().hex, b"toolsmith-gridfs-probe"
        )
        try:
            content = await (await bucket.open_download_stream(file_id)).read()
            if content != b"toolsmith-gridfs-probe":
                raise ValueError("GridFS content mismatch")
            return "round trip"
        finally:
            await bucket.delete(file_id)

    async def fusion():
        vector = {
            "$vectorSearch": {
                "index": "tools_vec",
                "path": "embedding",
                "queryVector": [1.0] + [0.0] * (args.text_dims - 1),
                "numCandidates": 20,
                "limit": 5,
                "filter": {"user_id": "__toolsmith_verification__", "status": "active"},
            }
        }
        search = {
            "$search": {
                "index": "tools_text",
                "compound": {
                    "must": [{"text": {"query": "probe", "path": "title"}}],
                    "filter": [
                        {"equals": {"path": "user_id", "value": "__toolsmith_verification__"}}
                    ],
                },
            }
        }
        pipeline = [
            {"$rankFusion": {"input": {"pipelines": {"vector": [vector], "text": [search]}}}}
        ]
        await (await db.tools.aggregate(pipeline)).to_list(length=None)
        return "vector + text pipeline accepted"

    await check("server >= 8.1", version)
    await check("sessions change stream", lambda: stream("sessions"))
    await check("frames change stream", lambda: stream("frames"))
    await check("GridFS", gridfs)
    await check("$rankFusion + $vectorSearch", fusion)
    report += [
        {
            "check": "Atlas index quota",
            "status": "UNVERIFIED",
            "detail": "Confirm project tier quota in Atlas",
        },
        {
            "check": "Voyage multimodal model and dimension",
            "status": "UNVERIFIED",
            "detail": "Requires P2 provider verification",
        },
    ]
    return report


async def main(args):
    try:
        print(json.dumps(await verify(args), indent=2))
    finally:
        await close_client()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-dims", type=int, default=1024)
    asyncio.run(main(parser.parse_args()))
