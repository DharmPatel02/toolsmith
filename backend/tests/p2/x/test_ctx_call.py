"""P2.3.6: composed UC2 tool calls `extract_method` inside the sandbox via ctx.call."""
import pytest
from mongomock_motor import AsyncMongoMockClient

from app.forge import deps
from app.gate import service as gate
from app.gate.testkit import run_tests_locally
from app.sandbox import run_in_sandbox
from app.trust import promote
from tests.p2.c.test_promote import staging_txn
from tests.p2.x.fixtures.uc2_tools import EXTRACT_METHOD, PAPER_DIGEST, PAPER_DIGEST_TESTS

A = "data/artifacts/uc2"
SPEC = {"name": "paper_digest", "title": "Paper digest", "purpose": "Five key facts from a paper.",
        "params_schema": {"type": "object", "properties": {"paper": {"type": "string", "format": "file"}},
                          "required": ["paper"]},
        "requires": {"scopes": [], "deps": [], "tools": ["extract_method"]}, "keywords": ["paper"],
        "derivation": {"observed_tier": "T0", "execution_path": "api"}, "outputs": {"files": []}}


@pytest.fixture
def env(monkeypatch):
    db = AsyncMongoMockClient()["ctx_call"]
    deps.use_db(db)

    async def pub(u, t, d):
        pass
    deps.use_publisher(pub)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setattr(promote, "_run_in_transaction", staging_txn)
    yield db
    deps.use_db(None)
    deps.use_publisher(None)


async def _seed_extract_method(db):
    await db.tools.insert_one({"_id": "tool_em", "user_id": "u_1", "name": "extract_method", "status": "active",
                               "active_version": 1})
    await db.tool_versions.insert_one({"_id": "tool_em@v1", "tool_id": "tool_em", "code": EXTRACT_METHOD,
                                       "requires": {"tools": []}})


def _cand():
    return {"_id": "cand_uc2", "user_id": "u_1", "spec": SPEC, "code": PAPER_DIGEST, "tests": PAPER_DIGEST_TESTS,
            "requires": SPEC["requires"], "params_schema": SPEC["params_schema"], "derivation": SPEC["derivation"],
            "status": "gating", "origin": {}, "evidence_inputs": [f"{A}/paper1.txt", f"{A}/paper2.txt"]}


@pytest.mark.asyncio
async def test_ctx_call_runs_dependency_in_sandbox():
    from app.forge.spec import resolve_artifact

    r = await run_in_sandbox(PAPER_DIGEST, "run", {"paper": "paper"},
                             {"paper": str(resolve_artifact(f"{A}/paper2.txt"))}, "dry_run", [],
                             deps={"extract_method": EXTRACT_METHOD})
    assert r.ok, r.error
    assert r.output["params"]["method"].startswith("Our approach, Masked Patch Pretraining")


@pytest.mark.asyncio
async def test_missing_dependency_fails_closed():
    r = await run_in_sandbox(PAPER_DIGEST, "run", {"paper": "paper"}, {"paper": "Title: x\n"}, "dry_run", [])
    assert not r.ok and "dependency 'extract_method' is not mounted" in r.error


def test_unit_tests_fake_the_dependency():
    assert run_tests_locally(PAPER_DIGEST, PAPER_DIGEST_TESTS)["failed"] == []


@pytest.mark.asyncio
async def test_gate_replays_composed_tool_and_promote_records_lineage(env):
    db = env
    await _seed_extract_method(db)
    await db.candidates.insert_one(_cand())
    v = await gate.run_gate("cand_uc2")
    assert v["decision"] == "passed", v["reason"]
    assert [c["label"] for c in v["checks"]["replay"]["cases"]] == ["paper1", "paper2"]
    tool_id = await promote.promote("cand_uc2", "u_1")
    tool = await db.tools.find_one({"_id": tool_id})
    assert tool["lineage"]["calls"] == ["tool_em"]
    assert await deps.dependents("u_1", "tool_em") == [tool_id]


@pytest.mark.asyncio
async def test_gate_fails_closed_without_the_dependency(env):
    db = env
    await db.candidates.insert_one(_cand())
    v = await gate.run_gate("cand_uc2")
    assert v["decision"] == "failed" and "dependency 'extract_method' is not an active tool" in v["reason"]


@pytest.mark.asyncio
async def test_replay_catches_a_wrong_extraction(env):
    db = env
    await _seed_extract_method(db)
    await db.candidates.insert_one({**_cand(), "code": PAPER_DIGEST.replace('params["title"]', 'params["title"]')
                                    .replace('"main_result": ["results", "findings"]', '"main_result": ["abstract"]')})
    v = await gate.run_gate("cand_uc2")
    assert v["decision"] == "failed" and "params: 'main_result'" in v["reason"]
