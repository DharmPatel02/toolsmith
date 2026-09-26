"""P4.2.3 / P4.2.4: analyze_idea, POST /ideas, concierge feedback + approve_change.

P1/P2 services are stubbed at `app.forge.deps` (the single seam P2 uses), so these tests don't
depend on STUB_MODE fixtures or a live Atlas.
"""

import httpx
import pytest
from app import llm
from app.concierge import actions, ideas
from app.concierge import service as concierge
from app.forge import deps
from app.routers import p3_ideas
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient

DRAFT = {
    "feasible": True,
    "name": "daily stock alert",
    "title": "Daily stock alert",
    "purpose": "Flag products with fewer than 5 units in stock",
    "params": [{"name": "catalog url", "type": "string"}, {"name": "threshold", "type": "integer"}],
    "scopes": ["net:localhost:8081", "write:outputs"],
    "deps": ["bs4", "pandas", "requests"],
    "minutes_per_run": 6,
    "runs_per_week": 5,
}


@pytest.fixture
def env(monkeypatch):
    db = AsyncMongoMockClient()["p3_test"]
    deps.use_db(db)
    events = []

    async def publisher(user_id, type, data):
        events.append((type, data))

    deps.use_publisher(publisher)
    state = {"hits": [], "episodes": [], "forged": []}

    async def search_tools(user_id, query, k=5):
        return state["hits"]

    async def recall_episodes(user_id, query, k=5):
        return state["episodes"]

    async def fake_complete(tier, messages, json_schema=None, **kw):
        return llm.LLMResult(text="", json=dict(DRAFT), tokens_in=300, tokens_out=120)

    async def fake_forge(user_id, spec, origin):
        state["forged"].append((spec, origin))
        return "cand_idea1"

    monkeypatch.setattr(deps, "search_tools", search_tools)
    monkeypatch.setattr(deps, "recall_episodes", recall_episodes)
    monkeypatch.setattr(ideas.llm, "complete", fake_complete)
    import app.forge.service as forge_service

    monkeypatch.setattr(forge_service, "forge_from_spec", fake_forge)
    yield db, state, events
    deps.use_db(None)
    deps.use_publisher(None)


async def test_idea_covered_by_existing_tool(env):
    db, state, _ = env
    state["hits"] = [{"tool_id": "tool_uc1", "name": "weekly_sales_rollup", "score": 0.91}]
    res = await ideas.analyze_idea("u_1", "every Monday I build the sales dashboard from the xlsx")
    assert res["covered_by_tool_id"] == "tool_uc1" and res["spec"] is None
    assert await db.ideas.count_documents({"_id": res["idea_id"]}) == 1


async def test_new_idea_returns_spec_and_confirm_forges(env):
    db, state, _ = env
    state["hits"] = [{"tool_id": "tool_uc3", "name": "competitor_price_sweep", "score": 0.55}]
    res = await ideas.analyze_idea("u_1", "alert me when a product drops below 5 in stock")
    spec = res["spec"]
    assert res["covered_by_tool_id"] is None and res["feasible"]
    assert spec["name"] == "daily_stock_alert"
    assert set(spec["params_schema"]["properties"]) == {"catalog_url", "threshold"}
    assert spec["requires"]["deps"] == ["bs4", "pandas"]  # "requests" is not allow-listed
    assert res["related_tool_id"] == "tool_uc3"
    assert res["est_minutes_saved_week"] == 30.0  # no history -> 6 min x 5 runs
    assert not state["forged"]  # nothing is built without confirmation

    confirmed = await ideas.analyze_idea("u_1", "", confirm=True, idea_id=res["idea_id"])
    assert confirmed["candidate_id"] == "cand_idea1"
    assert state["forged"][0][1]["idea_id"] == res["idea_id"]
    assert (await db.ideas.find_one({"_id": res["idea_id"]}))["status"] == "forging"


async def test_savings_come_from_history_when_available(env):
    _, state, _ = env
    state["episodes"] = [
        {"session_id": s, "date": d, "minutes": 9, "tokens": 18000, "score": 0.9}
        for s, d in [("s1", "2026-09-07"), ("s2", "2026-09-14"), ("s3", "2026-09-21")]
    ] + [{"session_id": "noise", "date": "2026-09-22", "minutes": 60, "tokens": 1, "score": 0.2}]
    res = await ideas.analyze_idea("u_1", "stock alert")
    assert res["est_minutes_saved_week"] == 9.0  # 27 relevant minutes over 3 weeks; noise ignored


async def test_post_ideas_route(env):
    app = FastAPI()
    app.include_router(p3_ideas.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/ideas", json={"text": "alert me on low stock"})
        assert r.status_code == 200 and r.json()["spec"]["name"] == "daily_stock_alert"
        assert (await c.post("/ideas", json={"text": "  "})).status_code == 422


async def test_feedback_and_approve_change(env):
    db, _, events = env
    fb = await actions.submit_feedback(
        "u_1", tool_id="tool_uc1", decision="edit", reason="also export PDF"
    )
    assert (
        fb["ok"]
        and await db.feedback.count_documents({"tool_id": "tool_uc1", "decision": "edit"}) == 1
    )
    assert "error" in await actions.submit_feedback("u_1", decision="edit")

    await db.policy.insert_one(
        {
            "_id": "policy:u_1",
            "version": 1,
            "thresholds": {"T_high": 0.82},
            "changes": [
                {
                    "id": "chg_2",
                    "field": "thresholds.T_high",
                    "from": 0.82,
                    "to": 0.78,
                    "direction": "loosen",
                    "because": "12 accepted found-routes",
                    "status": "pending",
                }
            ],
        }
    )
    res = await actions.approve_change("u_1", "chg_2")
    policy = await db.policy.find_one({"_id": "policy:u_1"})
    assert res["ok"] and policy["thresholds"]["T_high"] == 0.78
    assert policy["changes"][0]["status"] == "applied" and policy["version"] == 2
    assert events[-1][0] == "policy_changed" and events[-1][1]["status"] == "applied"
    assert (await actions.approve_change("u_1", "chg_2"))["already"] == "applied"
    assert "error" in await actions.approve_change("u_1", "nope")


async def test_chat_routes_idea_tool_and_returns_idea_card(env, monkeypatch):
    rounds = []

    async def chat_llm(tier, messages, json_schema=None, *, tools=None, **kw):
        if json_schema:  # analyze_idea's own call (same app.llm module)
            return llm.LLMResult(text="", json=dict(DRAFT))
        rounds.append(messages)
        if not any(m["role"] == "tool" for m in messages):
            return llm.LLMResult(
                text="",
                tool_calls=[
                    {"id": "c1", "name": "analyze_idea", "arguments": {"text": "low stock alert"}}
                ],
            )
        return llm.LLMResult(text="That's new; here is a spec. Say yes to build it.")

    monkeypatch.setattr(concierge.llm, "complete", chat_llm)
    reply = await concierge.chat("u_1", None, "can you alert me on low stock?")
    assert reply["cards"][0]["kind"] == "idea"
    assert reply["cards"][0]["idea"]["spec"]["name"] == "daily_stock_alert"
    assert "spec" in reply["reply"]
