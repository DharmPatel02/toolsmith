"""P2.3.3: POST /race -> both sides stream race_step and finish with final numbers."""
import asyncio

import httpx
import pytest
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient

from app import llm
from app.baseline import service as race
from app.forge import deps
from app.routers import p2_race
from tests.p2.c.test_gate import UC1_CODE, UC1_TESTS

WEEK4 = "data/artifacts/uc1/week4.xlsx"
BUGGY = '''
def run(ctx):
    df = ctx.read_table("file")
    return {"tables": {"pivot": df.groupby("Region")["Amount"].sum().reset_index().to_dict("records")}}
'''
FIXED = UC1_CODE.replace("def run(ctx, **params):\n    week = params.get(\"week\", \"\")",
                         "def run(ctx):\n    week = \"4\"")


class ScriptedAgent:
    """Answers like a lean model would: look, try, fail, fix, finish."""
    def __init__(self):
        self.script = [
            [("list_inputs", {})],
            [("preview_table", {"name": "file", "rows": 3})],
            [("run_python", {"code": BUGGY})],
            [("run_python", {"code": FIXED})],
            [("finish", {"summary": "4 regions, pivot + bar chart"})],
        ]
        self.seen_tool_results = []

    async def complete(self, tier, messages, json_schema=None, *, tools=None, **kw):
        assert tier == "lean" and tools
        self.seen_tool_results += [m["content"] for m in messages if m["role"] == "tool"][len(self.seen_tool_results):]
        calls = self.script.pop(0)
        return llm.LLMResult(text="", tokens_in=1500, tokens_out=300, usd=0.001, tool_calls=[
            {"id": f"c{len(self.script)}_{i}", "name": n, "arguments": a} for i, (n, a) in enumerate(calls)])


@pytest.fixture
def env(monkeypatch):
    db = AsyncMongoMockClient()["race_test"]
    deps.use_db(db)
    events = []

    async def pub(u, t, d):
        events.append((t, d))
    deps.use_publisher(pub)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    yield db, events, monkeypatch
    deps.use_db(None)
    deps.use_publisher(None)


async def _seed_uc1_tool(db):
    from app import embeddings

    vec = (await embeddings.embed(["Weekly sales rollup"]))[0]
    await db.tools.insert_one({"_id": "tool_uc1", "user_id": "u_1", "name": "weekly_sales_rollup", "status": "active",
                               "trust": "supervised", "active_version": 1, "embedding": vec})
    await db.tool_versions.insert_one({
        "_id": "tool_uc1@v1", "tool_id": "tool_uc1", "code": UC1_CODE, "tests": UC1_TESTS,
        "params_schema": {"type": "object", "properties": {"file": {"type": "string", "format": "file"},
                                                           "week": {"type": "string"}}},
        "requires": {"scopes": ["write:outputs"], "deps": ["pandas"]}})


@pytest.mark.asyncio
async def test_race_both_sides_stream_and_finish(env):
    db, events, mp = env
    await _seed_uc1_tool(db)
    agent = ScriptedAgent()
    mp.setattr(race.llm, "complete", agent.complete)
    app = FastAPI()
    app.include_router(p2_race.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/race", params={"wait": "true"},
                         json={"intent": "weekly sales dashboard for week 4", "inputs": {"file": WEEK4, "week": "4"}})
        assert r.status_code == 200, r.text
        out = r.json()
        stored = (await c.get(f"/race/{out['race_id']}")).json()

    assert out["baseline"]["ok"] and out["tool"]["ok"]
    assert out["baseline"]["steps"] == 5 and out["baseline"]["tokens"] == 5 * 1800
    assert out["tool"]["steps"] == 2 and out["tool"]["tokens"] == 0
    # the agent really ran its code: the buggy try failed, the fix produced the pivot
    assert "KeyError" in agent.seen_tool_results[2] and "West" in agent.seen_tool_results[3]
    assert stored["status"] == "done" and stored["summary"]["baseline"]["steps"] == 5

    steps = [d for t, d in events if t == "race_step"]
    for side, n in (("baseline", 5), ("tool", 2)):
        mine = [s for s in steps if s["side"] == side]
        assert [s["step"] for s in mine] == list(range(1, n + 1))
        assert [s["done"] for s in mine] == [False] * (n - 1) + [True]
        assert all(s["race_id"] == out["race_id"] and "elapsed_ms" in s and "tokens" in s for s in mine)
    assert steps[-1]["done"] or any(s["done"] for s in steps if s["side"] == "tool")


@pytest.mark.asyncio
async def test_race_returns_at_once_and_baseline_model_error_still_finishes(env):
    db, events, mp = env

    async def down(*a, **k):
        raise llm.LLMError("no key")
    mp.setattr(race.llm, "complete", down)
    app = FastAPI()
    app.include_router(p2_race.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/race", json={"intent": "x", "inputs": {}})
    rid = r.json()["race_id"]
    for _ in range(50):
        if (await db.races.find_one({"_id": rid}))["status"] == "done":
            break
        await asyncio.sleep(0.05)
    race_doc = await db.races.find_one({"_id": rid})
    assert race_doc["status"] == "done" and race_doc["baseline"]["error"] == "no key"
    assert race_doc["tool"]["route"] == "not_found"
    done = {d["side"] for t, d in events if t == "race_step" and d["done"]}
    assert done == {"baseline", "tool"}
