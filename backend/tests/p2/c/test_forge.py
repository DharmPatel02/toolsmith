"""P2.1.4-P2.1.8: spec (+derivation), code + checks + repair, TOOL.md, forge service + endpoints.
LLM is mocked with canned UC1 answers; Mongo is mongomock."""
import json
from pathlib import Path

import httpx
import pandas as pd
import pytest
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient

from app import llm
from app.forge import deps, service, spec, tutorial
from app.prompts import forge_prompts as fp
from app.routers import p2_forge

FIX = Path(__file__).parent / "fixtures"
UC1_CODE = (FIX / "uc1_tool.py").read_text()
UC1_TESTS = (FIX / "uc1_tests.py").read_text()

PATTERN_UC1 = {  # fixtures/pattern_uc1.json (TASKS §3.6)
    "_id": "pat_uc1", "user_id": "u_1", "status": "proposed",
    "title": "Weekly sales dashboard from Monday xlsx",
    "signature": ["file.open:xlsx", "table.rename:cols", "table.dropna", "table.cast", "table.pivot:2col",
                  "chart.bar", "export.html"],
    "static_steps": {"rename_map": {"reg": "Region", "amt": "Amount"},
                     "pivot": {"index": "Region", "values": "Amount", "aggfunc": "sum"}},
    "dynamic_params": [{"name": "file", "type": "file"}, {"name": "week", "type": "string"}],
    "support": 3, "distinct_days": 3, "variance": 0.08, "periodicity": 0.9, "burstiness": 0.1,
    "avg_minutes": 9, "avg_tokens": 18000, "value": 22.4,
    "evidence_session_ids": ["s_w1_mon", "s_w2_mon", "s_w3_mon"],
}

CANNED_SPEC = {  # note: model "forgot" the week param and the write scope; normalize must fix
    "name": "weekly_sales_rollup", "title": "Weekly sales rollup",
    "purpose": "Turns the Monday sales workbook into a region pivot and a bar-chart dashboard.",
    "params_schema": {"type": "object", "properties": {"file": {"type": "string"}}, "required": ["file"]},
    "outputs": {"tables": ["pivot"], "chart": True, "files": ["dashboard.html"]},
    "requires": {"scopes": [], "deps": ["pandas", "openpyxl", "requests"], "tools": []},
    "keywords": ["sales", "weekly", "pivot", "region", "dashboard"],
    "steps": ["open xlsx", "rename columns", "drop empty rows", "cast amounts", "pivot by region",
              "bar chart", "export html"],
    "derivation": {"observed_tier": "T2", "execution_path": "api"},
    "not_automatable": None,
}
GOOD_TUTORIAL = "# Weekly sales rollup\n\n" + "\n\n".join(f"## {h}\nSome words here." for h in fp.TUTORIAL_HEADINGS)


class FakeLLM:
    def __init__(self, code_replies):
        self.code_replies = list(code_replies)
        self.calls = []

    async def complete(self, tier, messages, json_schema=None, **kw):
        self.calls.append((tier, json_schema))
        if json_schema is fp.SPEC_SCHEMA:
            return llm.LLMResult(text="", json=json.loads(json.dumps(CANNED_SPEC)), tokens_in=100, usd=0.01)
        if json_schema is fp.CODE_SCHEMA:
            code, tests = self.code_replies.pop(0)
            return llm.LLMResult(text=json.dumps({"code": code, "tests": tests}), json={"code": code, "tests": tests},
                                 tokens_in=200, usd=0.02)
        return llm.LLMResult(text=GOOD_TUTORIAL, tokens_in=50, usd=0.001)


@pytest.fixture
def env(monkeypatch, tmp_path):
    db = AsyncMongoMockClient()["toolsmith_test"]
    deps.use_db(db)
    events = []

    async def pub(user_id, type, data):
        events.append((type, data))
    deps.use_publisher(pub)
    xlsx = tmp_path / "week1.xlsx"
    pd.DataFrame({"date": ["2026-09-07"] * 3, "reg": ["N", "S", "N"], "amt": ["1", 2.5, None]}).to_excel(xlsx, index=False)
    yield db, events, xlsx
    deps.use_db(None)
    deps.use_publisher(None)


def _use_llm(monkeypatch, fake):
    for mod in (spec, service, tutorial):
        monkeypatch.setattr(mod.llm, "complete", fake.complete)


def test_normalize_spec_matches_pattern():
    s = spec.normalize_spec(CANNED_SPEC, PATTERN_UC1)
    props = s["params_schema"]["properties"]
    assert set(props) == {"file", "week"} and props["file"]["format"] == "file"
    assert s["params_schema"]["required"] == ["file", "week"]
    assert s["derivation"]["execution_path"] == "api"
    assert "requests" not in s["requires"]["deps"] and "write:outputs" in s["requires"]["scopes"]
    assert spec.input_names(s) == ["file"]


def test_tutorial_checks_and_fallback():
    assert tutorial.tutorial_problems(GOOD_TUTORIAL) == []
    assert tutorial.tutorial_problems("## What it does\n" + "word " * 400)
    fb = tutorial.fallback_tutorial(spec.normalize_spec(CANNED_SPEC, PATTERN_UC1), {"inputs": {"file": "week1.xlsx"}})
    assert tutorial.tutorial_problems(fb) == []


@pytest.mark.asyncio
async def test_forge_uc1_with_one_repair(env, monkeypatch):
    db, events, xlsx = env
    fake = FakeLLM([("import os\n" + UC1_CODE, UC1_TESTS), (UC1_CODE, UC1_TESTS)])
    _use_llm(monkeypatch, fake)
    cid = await service.forge_from_pattern_doc({**PATTERN_UC1, "artifact_paths": [str(xlsx)]})
    cand = await db.candidates.find_one({"_id": cid})
    assert cand["status"] == "gating" and cand["attempts"] == 2 and cand["problems"] == []
    assert cand["derivation"] == {"observed_tier": "T2", "execution_path": "api"}
    assert set(cand["params_schema"]["properties"]) == {"file", "week"}
    assert cand["code"] == UC1_CODE and "def test_" in cand["tests"] and cand["tutorial_md"].startswith("# ")
    assert cand["cost"]["calls"] == 4 and cand["cost"]["usd"] == pytest.approx(0.051)
    assert cand["evidence_inputs"] == [str(xlsx)]
    assert [e[0] for e in events] == ["forge_started", "forged"]
    assert events[1][1]["execution_path"] == "api"
    code_call_tiers = [t for t, s in fake.calls if s is fp.CODE_SCHEMA]
    assert code_call_tiers == ["heavy", "heavy"]


@pytest.mark.asyncio
async def test_forge_gives_up_after_3_repairs(env, monkeypatch):
    db, _, _ = env
    bad = ("import os\n" + UC1_CODE, UC1_TESTS)
    _use_llm(monkeypatch, FakeLLM([bad] * 4))
    cid = await service.forge_from_pattern_doc(PATTERN_UC1)
    cand = await db.candidates.find_one({"_id": cid})
    assert cand["status"] == "failed" and cand["attempts"] == 4
    assert any("import not allowed: os" in p for p in cand["problems"])


@pytest.mark.asyncio
async def test_evidence_inputs_from_sessions(env):
    db, _, _ = env
    await db.sessions.insert_many([
        {"_id": "s_w1_mon", "artifacts": {"inputs": ["data/artifacts/uc1/week1.xlsx"]}},
        {"_id": "s_w2_mon", "artifacts": {"inputs": [{"path": "data/artifacts/uc1/week2.xlsx"}]}},
    ])
    assert await service.evidence_inputs(PATTERN_UC1) == ["data/artifacts/uc1/week1.xlsx",
                                                          "data/artifacts/uc1/week2.xlsx"]


@pytest.mark.asyncio
async def test_endpoints(env, monkeypatch):
    _db, _, _ = env
    _use_llm(monkeypatch, FakeLLM([(UC1_CODE, UC1_TESTS)]))
    app = FastAPI()
    app.include_router(p2_forge.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/dev/forge?wait=true", json={"pattern": PATTERN_UC1})
        cid = r.json()["candidate_id"]
        cand = (await c.get(f"/candidates/{cid}")).json()
        assert cand["status"] == "gating" and cand["spec"]["name"] == "weekly_sales_rollup"
        assert cand["verdict"] is None
        assert (await c.get("/candidates/nope")).status_code == 404
