import pytest
from mongomock_motor import AsyncMongoMockClient

from app.forge import deps
from app.trust.ladder import update_after_run


@pytest.fixture
def env():
    db = AsyncMongoMockClient()["trust_ladder_test"]
    deps.use_db(db)
    events = []

    async def pub(_user_id, event_type, data):
        events.append((event_type, data))

    deps.use_publisher(pub)
    yield db, events
    deps.use_db(None)
    deps.use_publisher(None)


async def _tool(db, trust="dry_run"):
    doc = {
        "_id": "tool_1",
        "user_id": "u_1",
        "trust": trust,
        "trust_streak": 0,
        "preview_confirms": 0,
        "trust_history": [],
    }
    await db.tools.insert_one(doc)
    await db.policy.insert_one({"_id": "policy:u_1", "success_streak_threshold": 8, "max_edit_rate": 0.1})
    return doc


@pytest.mark.asyncio
async def test_three_confirmed_previews_promote_to_supervised(env):
    db, events = env
    await _tool(db)

    for i in range(3):
        await update_after_run(
            {"_id": f"r{i}", "tool_id": "tool_1", "user_id": "u_1", "outcome": "success", "user_confirmed": True}
        )

    tool = await db.tools.find_one({"_id": "tool_1"})
    assert tool["trust"] == "supervised"
    assert tool["preview_confirms"] == 0
    assert events == [("trust_changed", {"tool_id": "tool_1", "from": "dry_run", "to": "supervised"})]


@pytest.mark.asyncio
async def test_eight_successes_create_autonomous_proposal_but_stay_supervised(env):
    db, events = env
    await _tool(db, trust="supervised")

    for i in range(8):
        await update_after_run({"_id": f"r{i}", "tool_id": "tool_1", "user_id": "u_1", "outcome": "success"})

    tool = await db.tools.find_one({"_id": "tool_1"})
    assert tool["trust"] == "supervised"
    assert tool["trust_streak"] == 8
    assert tool["trust_proposal"]["to"] == "autonomous"
    assert events == []


@pytest.mark.asyncio
async def test_supervised_failure_demotes_to_dry_run(env):
    db, events = env
    await _tool(db, trust="supervised")

    await update_after_run({"_id": "r1", "tool_id": "tool_1", "user_id": "u_1", "outcome": "failed"})

    tool = await db.tools.find_one({"_id": "tool_1"})
    assert tool["trust"] == "dry_run"
    assert tool["trust_streak"] == 0
    assert events == [("trust_changed", {"tool_id": "tool_1", "from": "supervised", "to": "dry_run"})]


@pytest.mark.asyncio
async def test_edit_rate_point_two_blocks_autonomous_proposal(env):
    db, _events = env
    await _tool(db, trust="supervised")

    await update_after_run({"_id": "e1", "tool_id": "tool_1", "user_id": "u_1", "outcome": "edited"})
    await update_after_run({"_id": "e2", "tool_id": "tool_1", "user_id": "u_1", "outcome": "edited"})
    for i in range(8):
        await update_after_run({"_id": f"s{i}", "tool_id": "tool_1", "user_id": "u_1", "outcome": "success"})

    tool = await db.tools.find_one({"_id": "tool_1"})
    assert tool["trust"] == "supervised"
    assert tool["trust_streak"] == 8
    assert tool.get("trust_proposal") is None
