"""P2.2.6: week-1 UC1 session -> correct canonical step sequence; dedupe, secret drop, vocab, fallback."""
import json
import os

import pytest
from dotenv import load_dotenv
from mongomock_motor import AsyncMongoMockClient

from app import llm
from app.forge import deps
from app.interpreter import jobs, stages, vocab
from app.interpreter import service as interp
from app.prompts import label_frames as lf
from tests.p2.c.test_forge import PATTERN_UC1
from tests.p2.c.uc1_frames import session_frames

load_dotenv()
UC1_VERBS = {  # what a good VLM says for each step frame
    "f_001": ("file.open", {"ext": "xlsx"}, 0.95), "f_002": ("table.rename", {"cols": 2}, 0.9),
    "f_003": ("table.dropna", {}, 0.85), "f_004": ("table.cast", {"to": "number"}, 0.8),
    "f_005": ("table.pivot", {"rows": "Region", "values": "Amount"}, 0.92),
    "f_006": ("chart.bar", {"x": "Region"}, 0.9), "f_007": ("export.html", {"ext": "html"}, 0.88),
}


class FakeVLM:
    def __init__(self, override=None):
        self.calls = []
        self.override = override or {}

    async def complete(self, tier, messages, json_schema=None, **kw):
        ids = [json.loads(p["text"].split("\n")[0][6:])["frame_id"] for p in messages[1]["content"]
               if p["type"] == "text" and p["text"].startswith("FRAME ")]
        self.calls.append(ids)
        steps = []
        for fid in ids:
            verb, shape, conf = self.override.get(fid, UC1_VERBS.get(fid, ("other", {}, 0.3)))
            steps.append({"frame_id": fid, "app": "excel", "verb": verb, "target": {"kind": "sheet", "name": "Sheet1"},
                          "args_shape": shape, "confidence": conf})
        return llm.LLMResult(text="", json={"steps": steps}, usd=0.002)


@pytest.fixture
def env(monkeypatch):
    db = AsyncMongoMockClient()["interp_test"]
    deps.use_db(db)
    events = []

    async def pub(u, t, d):
        events.append((t, d))
    deps.use_publisher(pub)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setenv("INTERPRETER_LABELS_DIR", "nonexistent-dir")
    monkeypatch.delenv("VOCAB_FROZEN", raising=False)
    yield db, events, monkeypatch
    deps.use_db(None)
    deps.use_publisher(None)


@pytest.mark.asyncio
async def test_week1_session_gives_uc1_sequence(env):
    db, events, mp = env
    await db.frames.insert_many(session_frames())
    fake = FakeVLM()
    mp.setattr(lf.llm, "complete", fake.complete)
    obs, stats = await interp.interpret_session_detailed("u_1", "s_w1_mon")

    assert [o["signature"] for o in obs] == PATTERN_UC1["signature"]
    assert stats["dropped"] == {"dhash": 2, "secret_credential": 1}  # f_dup + f_near; api_key frame
    assert stats["kept"] == 7 and stats["vlm_calls"] == 1 and stats["label_source"] == "vlm"
    assert fake.calls == [[f"f_{i:03d}" for i in range(1, 8)]]
    o = obs[4]
    assert o["evidence"]["frame_ids"] == ["f_005"] and o["evidence"]["tier"] == "T2"
    assert o["evidence"]["confidence"] == 0.92
    assert "PivotTable" in o["evidence"]["ocr_snippet"] and o["meta"] == {"user_id": "u_1", "source": "excel"}

    assert await db.frames.find_one({"_id": "f_secret"}) is None              # dropped, not blurred
    f5 = await db.frames.find_one({"_id": "f_005"})
    assert f5["label"]["signature"] == "table.pivot:2col" and f5["label"]["source"] == "vlm"
    assert len(f5["embedding"]) == 1024 and f5["interp"]["kept"] is True and f5["dhash"]
    assert (await db.frames.find_one({"_id": "f_dup"}))["interp"]["reason"] == "dhash"
    assert sum(1 for t, _ in events if t == "frame_labeled") == 7
    # idempotent: a second run finds nothing new
    assert await interp.interpret_session("u_1", "s_w1_mon") == []


@pytest.mark.asyncio
async def test_low_confidence_and_other_verbs(env):
    db, _, mp = env
    await db.frames.insert_many(session_frames())
    mp.setattr(lf.llm, "complete", FakeVLM({"f_004": ("table.cast", {}, 0.4),
                                            "f_003": ("other", {}, 0.9)}).complete)
    obs = await interp.interpret_session("u_1", "s_w1_mon")
    by = {o["evidence"]["frame_ids"][0]: o for o in obs}
    assert by["f_004"]["needs_review"] is True and by["f_005"]["needs_review"] is False
    assert by["f_003"]["signature"] == "other"


@pytest.mark.asyncio
async def test_vocab_alias_and_promotion(env):
    db, _, _ = env
    voc = [{"_id": "table.pivot", "status": "active", "aliases": []}]
    # fake embeddings are hash-based: a brand-new verb becomes a candidate, active after 3 sightings
    for i in range(3):
        await vocab.canonicalize([{"frame_id": f"f{i}", "verb": "other", "proposed_verb": "table.sort",
                                   "confidence": 0.9}], voc)
    doc = await db.action_vocab.find_one({"_id": "table.sort"})
    assert doc["seen"] == 3 and doc["status"] == "active" and len(doc["example_frames"]) == 3


@pytest.mark.asyncio
async def test_alias_when_similar(env):
    _, _, mp = env

    async def same_vec(texts, input_type="document"):
        return [[1.0, 0.0] for _ in texts]
    mp.setattr(vocab.embeddings, "embed", same_vec)
    s = {"frame_id": "fx", "verb": "other", "proposed_verb": "make.pivot", "confidence": 0.9}
    await vocab.canonicalize([s], [{"_id": "table.pivot", "status": "active", "aliases": []}])
    assert s["verb"] == "table.pivot" and s["aliased_from"] == "make.pivot"


@pytest.mark.asyncio
async def test_frozen_vocab_writes_nothing(env):
    db, _, mp = env
    mp.setenv("VOCAB_FROZEN", "1")
    await vocab.canonicalize([{"frame_id": "f", "verb": "other", "proposed_verb": "table.sort", "confidence": 1}],
                             [{"_id": "table.pivot", "status": "active"}])
    assert await db.action_vocab.count_documents({}) == 0


@pytest.mark.asyncio
async def test_hand_label_fallback_and_job(env, tmp_path):
    db, _, mp = env
    await db.frames.insert_many(session_frames())
    (tmp_path / "s_w1_mon.json").write_text(json.dumps({"steps": [
        {"frame_id": fid, "app": "excel", "verb": v, "args_shape": a, "confidence": c, "target": {}}
        for fid, (v, a, c) in UC1_VERBS.items()]}))
    mp.setenv("INTERPRETER_LABELS_DIR", str(tmp_path))

    async def no_vlm(*a, **k):
        raise AssertionError("VLM must not be called when hand labels exist")
    mp.setattr(lf.llm, "complete", no_vlm)
    out = await jobs.handle_interpret({"payload": {"user_id": "u_1", "session_id": "s_w1_mon"}})
    assert out["label_source"] == "hand" and out["observations"] == 7 and out["usd"] == 0


def test_region_diff():
    from tests.p2.c.uc1_frames import STEPS, frame_image
    a = stages.open_image(frame_image(*STEPS[0]))
    assert stages.region_diff(a, stages.open_image(frame_image(*STEPS[0], noise=3))) < stages.REGION_DIFF_MIN
    assert stages.region_diff(a, stages.open_image(frame_image(*STEPS[4]))) > stages.REGION_DIFF_MIN


def test_secret_rules():
    assert stages.secret_rule("password: hunter22") == "credential"
    assert stages.secret_rule("mail me at a.b@example.com") == "email"
    assert stages.secret_rule("card 4111 1111 1111 1111") == "card_number"
    assert stages.secret_rule("Sum of Amount 1240.50  9406.82  12345678901234") is None  # not Luhn


def test_fallback_signatures():
    assert vocab.fallback_signature("table.pivot", {"rows": "Region", "values": "Amount"}) == "table.pivot:2col"
    assert vocab.fallback_signature("file.open", {"ext": ".XLSX"}) == "file.open:xlsx"
    assert vocab.fallback_signature("chart.bar", {"x": "Region"}) == "chart.bar"
    # live VLM finding: file named in target, ext missing from args_shape
    assert vocab.fill_ext({"verb": "file.open", "target": {"name": "sales_w1.xlsx"}, "args_shape": {}}) == {"ext": "xlsx"}
    assert vocab.fill_ext({"verb": "table.pivot", "target": {"name": "a.xlsx"}, "args_shape": {}}) == {}


@pytest.mark.skipif(not os.getenv("LLM_VISION_MODEL"), reason="no LLM_VISION_MODEL in .env")
@pytest.mark.asyncio
async def test_week1_live_vlm(env):
    db, _, _ = env
    await db.frames.insert_many(session_frames())
    obs = await interp.interpret_session("u_1", "s_w1_mon")
    sigs = [o["signature"] for o in obs]
    assert "table.pivot:2col" in sigs and "chart.bar" in sigs and sigs[0] == "file.open:xlsx"
