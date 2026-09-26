"""Sandbox contract the gate relies on (TASKS §3.3 + P2_split requests)."""
from pathlib import Path

import pandas as pd
import pytest

from app.gate.testkit import build_test_program
from app.sandbox import run_in_sandbox

FIX = Path(__file__).parent / "fixtures"
UC1 = Path(__file__).resolve().parents[4] / "data" / "artifacts" / "uc1"
UC1_CODE = (FIX / "uc1_tool.py").read_text()


@pytest.mark.asyncio
async def test_uc1_tool_runs_with_kwargs_and_named_xlsx_input():
    r = await run_in_sandbox(UC1_CODE, "run", {"week": "1"}, {"file": str(UC1 / "week1.xlsx")},
                             "dry_run", ["write:outputs"])
    assert r.ok, r.error
    expected = pd.read_csv(UC1 / "expected" / "week1_pivot.csv").to_dict("records")
    assert r.output["tables"]["pivot"] == expected
    assert [w.path for w in r.intended_writes] == ["dashboard.html"]


@pytest.mark.asyncio
async def test_net_scope_is_per_domain():
    code = "def run(ctx, **params):\n    return {'html': ctx.fetch('http://evil.test/x')}\n"
    r = await run_in_sandbox(code, "run", {}, {}, "dry_run", ["net:localhost"], timeout_s=10)
    assert not r.ok and "net:evil.test" in r.error


@pytest.mark.asyncio
async def test_live_write_needs_scope(tmp_path):
    code = "def run(ctx, **params):\n    ctx.write_output('a.txt', 'x')\n    return {}\n"
    r = await run_in_sandbox(code, "run", {}, {}, "live", [], timeout_s=10)
    assert not r.ok and "write:outputs" in r.error
    r = await run_in_sandbox(code, "run", {}, {}, "dry_run", [], timeout_s=10)
    assert r.ok and r.intended_writes[0].path == "a.txt"


@pytest.mark.asyncio
async def test_unit_test_program_runs_through_runner():
    prog = build_test_program(UC1_CODE, (FIX / "uc1_tests.py").read_text())
    r = await run_in_sandbox(prog, "run_tests", {}, {}, "dry_run", [], timeout_s=30)
    assert r.ok, r.error
    assert r.output == {"total": 2, "passed": 2, "failed": []}
