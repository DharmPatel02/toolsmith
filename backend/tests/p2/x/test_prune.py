"""P2.3.3: 2 idle seeded tools get pruned; a depended-on idle tool is kept; toolbox count drops."""
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient

from app.forge import deps
from app.routers import p2_trust
from app.trust import jobs

OLD = datetime.now(UTC) - timedelta(days=40)


def _tool(tid, name, created=OLD, calls=()):
    return {"_id": tid, "user_id": "u_1", "name": name, "status": "active", "created_at": created,
            "lineage": {"calls": list(calls)}}


def _runs(tid, outcomes, days_ago=1):
    return [{"_id": f"{tid}_r{i}", "tool_id": tid, "outcome": o, "started_at": datetime.now(UTC) - timedelta(days=days_ago)}
            for i, o in enumerate(outcomes)]


@pytest.fixture
def env():
    db = AsyncMongoMockClient()["prune"]
    deps.use_db(db)
    events = []

    async def pub(u, t, d):
        events.append((t, d))
    deps.use_publisher(pub)
    yield db, events
    deps.use_db(None)
    deps.use_publisher(None)


@pytest.mark.asyncio
async def test_prune_with_safety(env):
    db, events = env
    await db.tools.insert_many([
        _tool("t_busy", "weekly_sales_rollup"),                          # used, healthy -> stays
        _tool("t_idle1", "old_csv_merge"), _tool("t_idle2", "pdf_renamer"),   # idle -> pruned
        _tool("t_flaky", "flaky_scraper"),                                # 20 % success -> pruned
        _tool("t_dep", "extract_method"),                                 # idle but depended on -> kept
        _tool("t_comp", "paper_digest", calls=["t_dep"]),
        _tool("t_new", "brand_new", created=datetime.now(UTC)),           # grace period -> stays
    ])
    await db.runs.insert_many(_runs("t_busy", ["success"] * 5) + _runs("t_flaky", ["failed"] * 4 + ["success"])
                              + _runs("t_comp", ["success"] * 3) + _runs("t_idle1", ["success"] * 3, days_ago=45))
    app = FastAPI()
    app.include_router(p2_trust.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        out = (await c.post("/prune")).json()

    assert sorted(p["tool_id"] for p in out["pruned"]) == ["t_flaky", "t_idle1", "t_idle2"]
    assert [k["tool_id"] for k in out["kept"]] == ["t_dep"]
    assert out["kept"][0]["kept_because"] == "kept: paper_digest depends on it"
    assert out["toolbox_count"] == 4
    assert (await db.tools.find_one({"_id": "t_idle1"}))["status"] == "deprecated"
    assert events[-1][0] == "pruned" and events[-1][1]["toolbox_count"] == 4


@pytest.mark.asyncio
async def test_prune_job_and_queue(env):
    db, _ = env
    await db.tools.insert_one(_tool("t_idle", "idle"))
    assert (await jobs.handle_prune({"payload": {"user_id": "u_1"}}))["pruned"][0]["tool_id"] == "t_idle"
    app = FastAPI()
    app.include_router(p2_trust.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        jid = (await c.post("/prune", params={"wait": "false"})).json()["job_id"]
    assert (await db.jobs.find_one({"_id": jid}))["type"] == "prune"
