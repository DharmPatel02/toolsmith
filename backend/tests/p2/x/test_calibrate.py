"""P2.3.5: the sweep picks sensible thresholds and the policy gets a logged change."""
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts import calibrate  # noqa: E402

from app.forge import deps  # noqa: E402

SCORED = (
    [{"expected": "t1", "top": "t1", "score": s} for s in (0.91, 0.88, 0.86, 0.84, 0.78)]   # 0.78: paraphrase
    + [{"expected": "t3", "top": "t3", "score": s} for s in (0.89, 0.85)]
    + [{"expected": "t3", "top": "t1", "score": 0.70}]                                       # wrong tool, lowish
    + [{"expected": None, "top": "t1", "score": s} for s in (0.62, 0.55, 0.48, 0.41)]         # nothing fits
)


def test_sweep_separates_right_hits_from_noise():
    r = calibrate.sweep(SCORED)
    assert 0.70 < r["T_high"] <= 0.78   # all right hits "found", the wrong-tool hit (0.70) is not
    assert 0.62 < r["T_low"] <= 0.70                              # related above all "nothing fits" scores
    assert r["f1_low"] == 1.0 and r["T_low"] <= r["T_high"]


@pytest.mark.asyncio
async def test_record_change_fallback_logs_the_change():
    db = AsyncMongoMockClient()["cal_test"]
    deps.use_db(db)
    events = []

    async def pub(u, t, d):
        events.append((t, d))
    deps.use_publisher(pub)
    try:
        await deps.record_change("u_1", "thresholds.T_high", 0.8, "loosen", "calibration on 15 pairs", ["calibration"])
    finally:
        deps.use_db(None)
        deps.use_publisher(None)
    pol = await db.policy.find_one({"_id": "policy:u_1"})
    assert pol["thresholds"]["T_high"] == 0.8 and pol["changes"][0]["origin_ids"] == ["calibration"]
    assert events[0][0] == "policy_changed" and events[0][1]["because"] == "calibration on 15 pairs"
