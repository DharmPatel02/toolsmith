"""P2.2.1: UC1 passes weeks 1-3 on the real artifacts; a tampered tool fails with a reason."""
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.forge import deps
from app.forge.spec import normalize_spec
from app.gate import service as gate
from tests.p2.c.test_forge import CANNED_SPEC, PATTERN_UC1

FIX = Path(__file__).parent / "fixtures"
UC1_CODE = (FIX / "uc1_tool.py").read_text()
UC1_TESTS = (FIX / "uc1_tests.py").read_text()
A = "data/artifacts/uc1"


def _sessions():
    return [{"_id": f"s_w{w}_mon", "artifacts": {
        "inputs": [f"{A}/week{w}.xlsx"],
        "outputs": [f"{A}/expected/week{w}_pivot.csv", f"{A}/expected/week{w}_chart.json"]}}
        for w in (1, 2, 3)]


def _candidate(**over):
    spec = normalize_spec(CANNED_SPEC, PATTERN_UC1)
    doc = {"_id": "cand_t", "user_id": "u_1", "spec": spec, "code": UC1_CODE, "tests": UC1_TESTS,
           "requires": spec["requires"], "status": "gating",
           "origin": {"pattern_id": "pat_uc1", "evidence_session_ids": ["s_w1_mon", "s_w2_mon", "s_w3_mon"]}}
    doc.update(over)
    return doc


@pytest.fixture
def env(monkeypatch):
    db = AsyncMongoMockClient()["gate_test"]
    deps.use_db(db)
    events = []

    async def pub(u, t, d):
        events.append((t, d))
    deps.use_publisher(pub)

    async def no_hits(user_id, query, k=5):
        return []
    monkeypatch.setattr(deps, "search_tools", no_hits)
    yield db, events
    deps.use_db(None)
    deps.use_publisher(None)


async def _gate(db, cand, sessions=True):
    if sessions:
        await db.sessions.insert_many(_sessions())
    await db.candidates.insert_one(cand)
    v = await gate.run_gate(cand["_id"])
    return v, await db.candidates.find_one({"_id": cand["_id"]})


@pytest.mark.asyncio
async def test_uc1_passes_weeks_1_to_3(env):
    db, events = env
    v, cand = await _gate(db, _candidate())
    assert v["decision"] == "passed", v["reason"]
    assert [c["label"] for c in v["checks"]["replay"]["cases"]] == ["s_w1_mon", "s_w2_mon", "s_w3_mon"]
    assert [c["params"]["week"] for c in v["checks"]["replay"]["cases"]] == ["1", "2", "3"]
    assert v["checks"]["unit"]["passed"] == 2
    assert v["checks"]["side_effects"]["writes"] == ["dashboard.html"]
    assert cand["status"] == "passed" and cand["verdict_id"] == v["_id"]
    assert events[-1][0] == "gate_passed"
    assert await db.verdicts.count_documents({}) == 1


@pytest.mark.asyncio
async def test_tampered_output_fails_with_reason(env):
    db, events = env
    tampered = UC1_CODE.replace('pivot["Amount"] = pivot["Amount"].round(2)',
                                'pivot["Amount"] = (pivot["Amount"] * 1.05).round(2)')
    v, cand = await _gate(db, _candidate(code=tampered))
    assert v["decision"] == "failed" and cand["status"] == "failed"
    assert "replay: 3/3 cases differ" in v["reason"] and "col 'Amount'" in v["reason"]
    assert events[-1][0] == "gate_failed"


@pytest.mark.asyncio
async def test_week3_drift_breaks_a_naive_tool(env):
    db, _ = env
    naive = UC1_CODE.replace('"region_name"', '"zzz"').replace('"amount", ', "")
    v, _ = await _gate(db, _candidate(code=naive, tests="def test_ok():\n    assert True\n"))
    bad = [c["label"] for c in v["checks"]["replay"]["cases"] if not c["ok"]]
    assert bad == ["s_w3_mon"]


@pytest.mark.asyncio
async def test_duplicate_and_scope_violations(env, monkeypatch):
    db, _ = env

    async def hit(user_id, query, k=5):
        return [{"tool_id": "t_old", "name": "sales_rollup_v0", "score": 0.97}]
    monkeypatch.setattr(deps, "search_tools", hit)
    spec = normalize_spec(CANNED_SPEC, PATTERN_UC1)
    v, _ = await _gate(db, _candidate(requires={**spec["requires"], "scopes": []}))
    assert not v["checks"]["duplicate"]["ok"] and "sales_rollup_v0" in v["reason"]
    assert v["checks"]["duplicate"]["decision"] == "merge"
    assert not v["checks"]["side_effects"]["ok"] and "write:outputs" in v["reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("score,decision,ok", [(0.85, "adapt", True), (0.40, "new", True), (0.95, "merge", False)])
async def test_dedupe_decision_is_recorded(env, monkeypatch, score, decision, ok):
    async def hit(user_id, query, k=5):
        return [{"tool_id": "t_other", "name": "regional_report", "score": score}]
    monkeypatch.setattr(deps, "search_tools", hit)
    dup = await gate.check_duplicate(_candidate())
    assert dup["decision"] == decision and dup["ok"] is ok
    # a heal re-gating its own tool is never a duplicate of itself
    assert (await gate.check_duplicate(_candidate(tool_id="t_other")))["decision"] == "new"


@pytest.mark.asyncio
async def test_fallback_to_evidence_inputs_without_sessions(env):
    db, _ = env
    cand = _candidate(origin={}, evidence_inputs=[f"{A}/week1.xlsx", f"{A}/week2.xlsx"])
    v, _ = await _gate(db, cand, sessions=False)
    assert v["decision"] == "passed", v["reason"]
    assert len(v["checks"]["replay"]["cases"]) == 2


def test_compare_helpers():
    assert gate.compare_table([{"Region": "N", "Amount": 1.004}], [{"Region": "N", "Amount": "1.00"}]) == []
    assert gate.compare_table([{"Region": "N"}], [{"Region": "N", "Amount": "1"}])[0].startswith("columns")
    assert gate.compare_chart({"type": "bar", "x": ["a"], "y": [1]}, {"type": "bar", "x": ["a"], "y": [1.0]}) == []
    assert gate.compare_chart(None, {"type": "bar"}) == ["no chart_spec in output"]
