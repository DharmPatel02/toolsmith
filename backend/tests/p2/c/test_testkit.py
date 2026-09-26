"""Unit-test runner explains failed asserts with actual vs expected values (feeds the repair prompt)."""
import pytest

from app.gate.testkit import build_test_program
from app.sandbox import run_in_sandbox

CODE = "def run(ctx, **params):\n    return {'rows': [{'Region': 'East', 'Amount': 3.5}]}\n"
TESTS = '''
def test_wrong_expectation():
    out = run(FakeCtx())
    assert out["rows"] == [
        {"Region": "East", "Amount": 4.0},
    ]


def test_wrong_prefix():
    ctx = FakeCtx()
    ctx.write_output("dashboard.html", "<!DOCTYPE html><html></html>")
    assert ctx.writes["dashboard.html"].startswith("<html>")


def test_ok():
    assert run(FakeCtx())["rows"][0]["Region"] == "East"
'''


@pytest.mark.asyncio
async def test_failed_assert_reports_values():
    r = await run_in_sandbox(build_test_program(CODE, TESTS), "run_tests", {}, {}, "dry_run", [])
    assert r.ok, r.error
    assert r.output["total"] == 3 and r.output["passed"] == 1
    errs = {f["name"]: f["error"] for f in r.output["failed"]}
    assert "out['rows'] was [{'Region': 'East', 'Amount': 3.5}]" in errs["test_wrong_expectation"]
    assert "expected [{'Region': 'East', 'Amount': 4.0}]" in errs["test_wrong_expectation"]
    assert "was '<!DOCTYPE html><html></html>'" in errs["test_wrong_prefix"]
