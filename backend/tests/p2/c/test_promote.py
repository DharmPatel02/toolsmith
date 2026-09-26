"""P2.2.3: promote in ONE transaction. Raise mid-way -> nothing written; normal -> all writes present.
mongomock has no sessions, so unit tests swap in a staging transaction (buffer, apply on commit);
the live test at the bottom proves real rollback on Atlas."""
import os

import httpx
import pytest
from dotenv import load_dotenv
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient

from app.forge import deps
from app.routers import p2_candidates
from app.trust import promote as pr
from tests.p2.c.test_gate import _candidate

load_dotenv()


async def staging_txn(db, ops):
    """Like a Mongo transaction: every op must succeed before anything is written."""
    for op in ops:
        if op.collection == "boom":
            raise RuntimeError("injected failure mid-transaction")
    for op in ops:
        await pr.apply_op(db, op)


@pytest.fixture
def env(monkeypatch):
    db = AsyncMongoMockClient()["promote_test"]
    deps.use_db(db)
    events = []

    async def pub(u, t, d):
        events.append((t, d))
    deps.use_publisher(pub)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setattr(pr, "_run_in_transaction", staging_txn)
    yield db, events, monkeypatch
    deps.use_db(None)
    deps.use_publisher(None)


async def _seed(db, **over):
    fields = {"status": "passed", "verdict_id": "ver_1", "pattern_id": "pat_uc1", "tutorial_md": "# t",
              "params_schema": {"type": "object", "properties": {}},
              "derivation": {"observed_tier": "T2", "execution_path": "api"}}
    cand = _candidate(**{**fields, **over})
    await db.candidates.insert_one(cand)
    await db.verdicts.insert_one({"_id": "ver_1", "candidate_id": cand["_id"]})
    await db.patterns.insert_one({"_id": "pat_uc1", "status": "accepted"})
    return cand


async def _counts(db):
    return {c: await db[c].count_documents({}) for c in ("tools", "tool_versions")}


@pytest.mark.asyncio
async def test_normal_promote_writes_everything(env):
    db, events, _ = env
    cand = await _seed(db)
    tool_id = await pr.promote(cand["_id"], "u_1")
    tool = await db.tools.find_one({"_id": tool_id})
    assert tool["trust"] == "dry_run" and tool["active_version"] == 1 and len(tool["embedding"]) == 1024
    tv = await db.tool_versions.find_one({"tool_id": tool_id})
    assert tv["derivation"]["execution_path"] == "api" and tv["verdict_id"] == "ver_1"
    assert (await db.verdicts.find_one({"_id": "ver_1"}))["tool_id"] == tool_id
    assert (await db.patterns.find_one({"_id": "pat_uc1"}))["status"] == "toolified"
    assert (await db.candidates.find_one({"_id": cand["_id"]}))["status"] == "approved"
    assert events == [("promoted", {"tool_id": tool_id, "candidate_id": "cand_t", "name": "weekly_sales_rollup",
                                    "version": 1, "trust": "dry_run"})]


@pytest.mark.asyncio
async def test_raise_midway_writes_nothing(env):
    db, events, mp = env
    cand = await _seed(db)
    real_plan = pr.plan_ops

    def plan_with_failure(*a, **k):
        ops = real_plan(*a, **k)
        return [*ops[:2], pr.Op("boom", "insert_one", ({},)), *ops[2:]]
    mp.setattr(pr, "plan_ops", plan_with_failure)
    with pytest.raises(RuntimeError):
        await pr.promote(cand["_id"], "u_1")
    assert await _counts(db) == {"tools": 0, "tool_versions": 0}
    assert (await db.candidates.find_one({"_id": cand["_id"]}))["status"] == "passed"
    assert (await db.patterns.find_one({"_id": "pat_uc1"}))["status"] == "accepted"
    assert events == []


@pytest.mark.asyncio
async def test_only_passed_can_be_approved_and_second_version(env):
    db, _, _ = env
    cand = await _seed(db, status="failed")
    with pytest.raises(pr.PromoteError):
        await pr.promote(cand["_id"], "u_1")
    await db.candidates.update_one({"_id": cand["_id"]}, {"$set": {"status": "passed"}})
    tool_id = await pr.promote(cand["_id"], "u_1")
    await db.candidates.insert_one({**cand, "_id": "cand_v2", "status": "passed", "tool_id": tool_id})
    assert await pr.promote("cand_v2", "u_1") == tool_id
    tool = await db.tools.find_one({"_id": tool_id})
    assert tool["active_version"] == 2 and await db.tool_versions.count_documents({"tool_id": tool_id}) == 2


@pytest.mark.asyncio
async def test_endpoints(env):
    db, _, _ = env
    cand = await _seed(db)
    await db.candidates.insert_one({**cand, "_id": "cand_r"})
    app = FastAPI()
    app.include_router(p2_candidates.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(f"/candidates/{cand['_id']}/approve")
        assert r.status_code == 200 and r.json()["tool_id"].startswith("tool_")
        assert (await c.post(f"/candidates/{cand['_id']}/approve")).status_code == 409
        assert (await c.post("/candidates/cand_r/reject", json={"reason": "not useful"})).json() == {"ok": True}
        assert (await db.candidates.find_one({"_id": "cand_r"}))["status"] == "rejected"


@pytest.mark.skipif(not os.getenv("MONGODB_URI"), reason="no MONGODB_URI (Atlas) in .env")
@pytest.mark.asyncio
async def test_live_atlas_rollback(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient

    db = AsyncIOMotorClient(os.environ["MONGODB_URI"])["toolsmith_p2_txn_test"]
    deps.use_db(db)
    monkeypatch.setattr(pr, "_run_in_transaction", pr._mongo_transaction)
    try:
        for c in ("candidates", "verdicts", "patterns", "tools", "tool_versions"):
            await db.create_collection(c) if c not in await db.list_collection_names() else None
            await db[c].delete_many({})
        cand = await _seed(db)
        real_plan = pr.plan_ops
        monkeypatch.setattr(pr, "plan_ops", lambda *a, **k: [*real_plan(*a, **k)[:2],
                                                              pr.Op("tools", "insert_one", ({"_id": None},)),
                                                              pr.Op("tools", "insert_one", ({"_id": None},))])
        with pytest.raises(Exception):  # noqa: B017 - duplicate key inside the transaction
            await pr.promote(cand["_id"], "u_1")
        assert await _counts(db) == {"tools": 0, "tool_versions": 0}
        monkeypatch.setattr(pr, "plan_ops", real_plan)
        assert await pr.promote(cand["_id"], "u_1")
        assert await _counts(db) == {"tools": 1, "tool_versions": 1}
    finally:
        await db.client.drop_database("toolsmith_p2_txn_test")
        deps.use_db(None)
