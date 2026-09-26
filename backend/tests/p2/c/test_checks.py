"""P2.1.5 static checks + the test kit, on the hand-written UC1 tool."""
from pathlib import Path

from app.forge import checks
from app.gate import testkit

FIX = Path(__file__).parent / "fixtures"
UC1_CODE = (FIX / "uc1_tool.py").read_text()
UC1_TESTS = (FIX / "uc1_tests.py").read_text()


def test_uc1_code_passes():
    assert checks.check_tool_code(UC1_CODE, ["pandas"]) == []
    assert checks.check_tests(UC1_TESTS) == []


def test_import_os_rejected():
    probs = checks.check_tool_code("import os\n\ndef run(ctx, **params):\n    return {}\n")
    assert any("import not allowed: os" in p for p in probs)


def test_other_violations():
    assert any("open()" in p for p in checks.check_tool_code("def run(ctx):\n    open('x')\n"))
    assert any("no top-level" in p for p in checks.check_tool_code("x = 1\n"))
    assert any("syntax" in p for p in checks.check_tool_code("def run(ctx:\n"))
    assert any("undefined" in p.lower() or "F821" in p for p in checks.check_tool_code("def run(ctx):\n    return y\n"))
    assert any("dependency" in p for p in checks.check_tool_code(UC1_CODE, ["requests"]))
    assert any("__class__" in p for p in checks.check_tool_code("def run(ctx):\n    return ctx.__class__\n"))


def test_kit_runs_uc1_tests():
    res = testkit.run_tests_locally(UC1_CODE, UC1_TESTS)
    assert res == {"total": 2, "passed": 2, "failed": []}


def test_kit_reports_failures():
    res = testkit.run_tests_locally(UC1_CODE, "def test_bad():\n    assert 1 == 2\n")
    assert res["passed"] == 0 and res["failed"][0]["name"] == "test_bad"
