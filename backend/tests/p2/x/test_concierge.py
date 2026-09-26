"""P2.3.6: "why did you suggest the dashboard tool?" cites dated episodes (from memory, not invented)."""
import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient

from app import embeddings, llm
from app.concierge import service as concierge
from app.forge import deps
from app.routers import p2_chat

INTENT = "weekly sales dashboard from the Monday xlsx"


class FakeLean:
    """Round 1: ask memory. Round 2: answer with exactly the dates memory returned."""
    def __init__(self):
        self.rounds = []

    async def complete(self, tier, messages, json_schema=None, *, tools=None, **kw):
        self.rounds.append(messages)
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        if not tool_msgs:
            return llm.LLMResult(text="", tokens_in=400, tokens_out=20, tool_calls=[
                {"id": "c1", "name": "recall_episodes", "arguments": {"query": INTENT}}])
        eps = json.loads(tool_msgs[-1]["content"])
        dates = sorted(e["date"] for e in eps)
        return llm.LLMResult(text=f"Because you built it by hand on {', '.join(dates)}.", tokens_in=600, tokens_out=40)


@pytest.fixture
def env(monkeypatch):
    db = AsyncMongoMockClient()["chat_test"]
    deps.use_db(db)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    yield db, monkeypatch
    deps.use_db(None)


@pytest.mark.asyncio
async def test_why_cites_dated_episodes_and_keeps_history(env):
    db, mp = env
    vec = (await embeddings.embed([INTENT]))[0]
    other = (await embeddings.embed(["reading a paper about transformers"]))[0]
    await db.sessions.insert_many(
        [{"_id": f"s_w{i}_mon", "user_id": "u_1", "started_at": datetime(2026, 9, 7 * i, 9, tzinfo=UTC),
          "intent_summary": INTENT, "minutes": 9, "tokens": 18000, "intent_embedding": vec} for i in (1, 2, 3)]
        + [{"_id": "s_noise", "user_id": "u_1", "started_at": datetime(2026, 9, 10, tzinfo=UTC),
            "intent_summary": "paper", "intent_embedding": other}])
    fake = FakeLean()
    mp.setattr(concierge.llm, "complete", fake.complete)

    app = FastAPI()
    app.include_router(p2_chat.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = (await c.post("/chat", json={"message": "why did you suggest the dashboard tool?"})).json()
        for d in ("2026-09-07", "2026-09-14", "2026-09-21"):
            assert d in r["reply"]
        assert r["tool_calls"] == [{"name": "recall_episodes", "arguments": {"query": INTENT}}]
        ep_card = r["cards"][0]
        assert ep_card["type"] == "episodes" and ep_card["items"][0]["score"] > 0.99
        assert {e["session_id"] for e in ep_card["items"][:3]} == {"s_w1_mon", "s_w2_mon", "s_w3_mon"}

        r2 = (await c.post("/chat", json={"message": "and before that?", "conversation_id": r["conversation_id"]}))
        assert r2.json()["conversation_id"] == r["conversation_id"]
    history = [m["content"] for m in fake.rounds[-2] if m["role"] in ("user", "assistant") and m.get("content")]
    assert history[:2] == ["why did you suggest the dashboard tool?", r["reply"]]
    conv = await db.conversations.find_one({"_id": r["conversation_id"]})
    assert len(conv["messages"]) == 4


@pytest.mark.asyncio
async def test_model_down_is_503(env):
    _, mp = env

    async def down(*a, **k):
        raise llm.LLMError("no key")
    mp.setattr(concierge.llm, "complete", down)
    app = FastAPI()
    app.include_router(p2_chat.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.post("/chat", json={"message": "hi"})).status_code == 503
