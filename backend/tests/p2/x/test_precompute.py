"""P2.3.4: precompute warms the real disk cache; a rerun makes no model calls; exported VLM labels
survive re-ingest (new frame ids) via dHash matching."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts import precompute  # noqa: E402

from app import llm  # noqa: E402
from app.forge import deps  # noqa: E402
from app.interpreter import service as interp  # noqa: E402
from app.prompts import forge_prompts as fp  # noqa: E402
from app.prompts import heal_prompts as hp  # noqa: E402
from app.prompts import label_frames as lf  # noqa: E402
from app.trust import promote, uc3_seed  # noqa: E402
from tests.p2.c.test_forge import CANNED_SPEC, GOOD_TUTORIAL  # noqa: E402
from tests.p2.c.test_gate import UC1_CODE, UC1_TESTS  # noqa: E402
from tests.p2.c.test_interpreter import UC1_VERBS  # noqa: E402
from tests.p2.c.uc1_frames import session_frames  # noqa: E402
from tests.p2.x.test_drift_heal import HEALED_CODE, HEALED_TESTS  # noqa: E402


class Transport:
    """Stands in for litellm (below llm.complete, so the real cache is used)."""
    def __init__(self):
        self.calls = 0

    async def __call__(self, model, messages, json_schema, tools, temperature, max_tokens):
        self.calls += 1
        if json_schema is fp.SPEC_SCHEMA:
            body = CANNED_SPEC
        elif json_schema is fp.CODE_SCHEMA:
            body = {"code": UC1_CODE, "tests": UC1_TESTS}
        elif json_schema is hp.HEAL_SCHEMA:
            body = {"diagnosis": "classes renamed", "code": HEALED_CODE, "tests": HEALED_TESTS}
        elif json_schema is lf.LABEL_FRAMES_SCHEMA:
            ids = [json.loads(p["text"].split("\n")[0][6:])["frame_id"] for p in messages[1]["content"]
                   if p["type"] == "text" and p["text"].startswith("FRAME ")]
            steps = []
            for fid in ids:  # precompute's frame ids are s_w1_mon_0000N, in UC1 step order
                verb, shape, conf = UC1_VERBS.get(f"f_{len(steps) + 1:03d}", ("other", {}, 0.3))
                steps.append({"frame_id": fid, "app": "excel", "verb": verb, "args_shape": shape, "confidence": conf,
                              "target": {}})
            body = {"steps": steps}
        else:
            body = None
        content = GOOD_TUTORIAL if body is None else json.dumps(body)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))],
                               usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50))


@pytest.fixture
def env(monkeypatch, tmp_path):
    for tier in ("LEAN", "HEAVY", "VISION"):
        monkeypatch.setenv(f"LLM_{tier}_MODEL", "openai/test-model")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_CACHE", raising=False)
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("INTERPRETER_LABELS_DIR", str(tmp_path / "labels"))
    monkeypatch.setenv("MOCKSITE_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(uc3_seed, "SNAPSHOT_DIR", tmp_path / "no_snapshots")
    monkeypatch.setattr(promote, "_run_in_transaction", promote._run_in_transaction)  # restored on undo
    kf = tmp_path / "keyframes" / "s_w1_mon"
    kf.mkdir(parents=True)
    for i, f in enumerate(d for d in session_frames() if d["_id"] in {f"f_{n:03d}" for n in range(1, 8)}):
        (kf / f"s_w1_mon_{i:05d}.webp").write_bytes(f["image"])
    monkeypatch.setattr(precompute, "KEYFRAMES", tmp_path / "keyframes")
    t = Transport()
    monkeypatch.setattr(llm, "_call", t)
    yield t, tmp_path
    deps.use_db(None)


@pytest.mark.asyncio
async def test_precompute_then_everything_is_cached(env):
    transport, tmp = env
    db = await precompute.setup_db(atlas=False)
    forge = await precompute.forge_uc1(db, None)
    heal = await precompute.heal_uc3(db)
    labels = await precompute.label_videos(db, relabel=False)
    assert forge["status"] == "passed" and heal["status"] == "healed"
    assert labels[0]["status"].startswith("7 steps")
    first = transport.calls
    assert first >= 5

    db2 = await precompute.setup_db(atlas=False)  # fresh DB, same cache
    again = await precompute.forge_uc1(db2, None)
    heal2 = await precompute.heal_uc3(db2)
    assert transport.calls == first                                   # no model call at all
    assert again["calls"] == again["cached_calls"] and again["forge_s"] < 5
    assert heal2["status"] == "healed" and heal2["cached_calls"] == heal2["calls"]

    # re-ingest with brand-new frame ids: the exported labels still apply, no VLM call
    label_file = json.loads((tmp / "labels" / "s_w1_mon.json").read_text())
    assert label_file["match"] == "dhash" and all(s["dhash"] for s in label_file["steps"])
    db3 = AsyncMongoMockClient()["reingest"]
    deps.use_db(db3)
    frames = [f for f in session_frames() if f["_id"] in {f"f_{n:03d}" for n in range(1, 8)}]
    for f in frames:
        f["_id"] = "new_" + f["_id"]
    await db3.frames.insert_many(frames)
    obs, stats = await interp.interpret_session_detailed("u_1", "s_w1_mon")
    assert transport.calls == first and stats["label_source"] == "precompute"
    assert [o["signature"] for o in obs] == ["file.open:xlsx", "table.rename:cols", "table.dropna", "table.cast",
                                             "table.pivot:2col", "chart.bar", "export.html"]
    assert all(o["evidence"]["frame_ids"][0].startswith("new_f_") for o in obs)
