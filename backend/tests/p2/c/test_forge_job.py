"""P2.2.2: forge job ends in passed or failed; gate failures feed the repair loop."""
import pytest
from mongomock_motor import AsyncMongoMockClient

from app.forge import codegen, deps, jobs, service, spec, tutorial
from tests.p2.c.test_forge import PATTERN_UC1, UC1_CODE, UC1_TESTS, FakeLLM
from tests.p2.c.test_gate import _sessions

WRONG = UC1_CODE.replace('pivot["Amount"] = pivot["Amount"].round(2)',
                         'pivot["Amount"] = (pivot["Amount"] * 1.05).round(2)')
WRONG_TESTS = "def test_runs():\n    assert callable(run)\n"


@pytest.fixture
def env(monkeypatch):
    db = AsyncMongoMockClient()["job_test"]
    deps.use_db(db)
    events = []

    async def pub(u, t, d):
        events.append(t)
    deps.use_publisher(pub)

    async def no_hits(user_id, query, k=5):
        return []
    monkeypatch.setattr(deps, "search_tools", no_hits)
    yield db, events, monkeypatch
    deps.use_db(None)
    deps.use_publisher(None)


def _use(monkeypatch, fake):
    for mod in (spec, service, tutorial, codegen):
        monkeypatch.setattr(mod.llm, "complete", fake.complete)


@pytest.mark.asyncio
async def test_gate_failure_is_repaired_then_passes(env):
    db, events, mp = env
    await db.sessions.insert_many(_sessions())
    await db.patterns.insert_one(PATTERN_UC1)
    fake = FakeLLM([(WRONG, WRONG_TESTS), (UC1_CODE, UC1_TESTS)])
    _use(mp, fake)
    out = await jobs.handle_forge({"type": "forge", "payload": {"pattern_id": "pat_uc1"}})
    assert out["status"] == "passed" and out["gate_attempts"] == 2
    cand = await db.candidates.find_one({"_id": out["candidate_id"]})
    assert cand["status"] == "passed" and cand["code"] == UC1_CODE and cand["attempt_no"] == 2
    assert cand["tutorial_example"]["inputs"] == {"file": "week3.xlsx", "week": "3"}
    assert events == ["forge_started", "forged", "gate_failed", "gate_passed"]
    assert await db.verdicts.count_documents({}) == 2


@pytest.mark.asyncio
async def test_gives_up_after_3_gate_repairs(env):
    db, _, mp = env
    await db.sessions.insert_many(_sessions())
    _use(mp, FakeLLM([(WRONG, WRONG_TESTS)] * 4))
    out = await jobs.handle_forge({"payload": {"pattern": PATTERN_UC1}})
    assert out["status"] == "failed" and "replay" in out["reason"]
    assert await db.verdicts.count_documents({}) == 4


@pytest.mark.asyncio
async def test_duplicate_is_not_repaired(env):
    db, _, mp = env
    await db.sessions.insert_many(_sessions())

    async def hit(user_id, query, k=5):
        return [{"tool_id": "t_x", "name": "same_tool", "score": 0.99}]
    mp.setattr(deps, "search_tools", hit)
    _use(mp, FakeLLM([(UC1_CODE, UC1_TESTS)]))
    out = await jobs.handle_forge({"payload": {"pattern": PATTERN_UC1}})
    assert out["status"] == "failed" and "duplicate" in out["reason"]
    assert await db.verdicts.count_documents({}) == 1


def test_register():
    seen = {}
    jobs.register(lambda t, h: seen.setdefault(t, h))
    assert seen == {"forge": jobs.handle_forge}
