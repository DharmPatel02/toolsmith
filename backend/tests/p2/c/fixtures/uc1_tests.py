# ruff: noqa: F821 - `run` and `FakeCtx` are injected by the test kit
import pandas as pd


def test_pivot_sums_by_region():
    df = pd.DataFrame({"reg": ["N", "S", "N", None], "amt": ["10", 5.5, 2, 1]})
    ctx = FakeCtx(tables={"file": df})
    out = run(ctx, week="1")
    assert out["tables"]["pivot"] == [{"Region": "N", "Amount": 12.0}, {"Region": "S", "Amount": 5.5}]
    assert out["chart_spec"]["type"] == "bar" and out["chart_spec"]["x"] == ["N", "S"]
    assert "dashboard.html" in ctx.writes


def test_renamed_columns():
    df = pd.DataFrame({"region_name": ["E"], "amount": [3]})
    out = run(FakeCtx(tables={"file": df}), week="3")
    assert out["tables"]["pivot"] == [{"Region": "E", "Amount": 3.0}]
