"""P2.1.4-P2.1.7 live: real models forge UC1; spec is api-path with file+week, code passes checks,
its own tests pass. Skipped until LLM keys are in .env."""
import os

import pandas as pd
import pytest
from dotenv import load_dotenv
from mongomock_motor import AsyncMongoMockClient

from app.forge import deps, service
from app.gate import testkit
from tests.p2.c.test_forge import PATTERN_UC1

load_dotenv()


@pytest.mark.skipif(not os.getenv("LLM_HEAVY_MODEL"), reason="no LLM_HEAVY_MODEL in .env")
@pytest.mark.asyncio
async def test_forge_uc1_live(tmp_path):
    db = AsyncMongoMockClient()["live"]
    deps.use_db(db)
    xlsx = tmp_path / "week1.xlsx"
    pd.DataFrame({"date": ["2026-09-07"] * 4, "reg": ["N", "S", "N", None],
                  "product": ["a", "b", "c", "d"], "amt": ["10", 2.5, 3, 1]}).to_excel(xlsx, index=False)
    try:
        cid = await service.forge_from_pattern_doc({**PATTERN_UC1, "artifact_paths": [str(xlsx)]})
        cand = await db.candidates.find_one({"_id": cid})
    finally:
        deps.use_db(None)
    assert cand["status"] == "gating", cand.get("problems")
    assert cand["derivation"]["execution_path"] == "api"
    assert {"file", "week"} <= set(cand["params_schema"]["properties"])
    res = testkit.run_tests_locally(cand["code"], cand["tests"])
    assert res["failed"] == [], res
