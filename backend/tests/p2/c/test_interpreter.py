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
from tests.p2.c.uc1_frames import frame_image, session_frames

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


def _week(n: int) -> list[dict]:
    """The week-1 frames re-recorded as week n: same screens, new ids and session."""
    out = []
    for f in session_frames():
        out.append({**f, "_id": f["_id"].replace("f_", f"w{n}_"), "session_id": f"s_w{n}_mon"})
    return out


@pytest.mark.asyncio
async def test_nn_label_copy_week3_needs_fewer_vlm_calls(env):
    db, _, mp = env
    await db.frames.insert_many(session_frames())
    fake = FakeVLM(override={f"w3_{i:03d}": UC1_VERBS[f"f_{i:03d}"] for i in range(1, 8)} | {"w3_new": ("other", {}, 0.3)})
    mp.setattr(lf.llm, "complete", fake.complete)
    _, week1 = await interp.interpret_session_detailed("u_1", "s_w1_mon")
    assert week1["vlm_frames"] == 7 and week1["nn_copied"] == 0

    w3 = _week(3)
    new = dict(session_frames()[4], _id="w3_new", session_id="s_w3_mon", ts="2026-09-21T09:30:00Z",
               image=frame_image("Conditional formatting > Color scales", (5, 5, 5), (2, 2)))  # never seen before
    await db.frames.insert_many(w3 + [new])
    obs, week3 = await interp.interpret_session_detailed("u_1", "s_w3_mon")
    assert week3["nn_copied"] == 7 and week3["vlm_frames"] == 1 < week1["vlm_frames"]
    assert fake.calls[-1] == ["w3_new"] and week3["label_source"] == "vlm+nn_copy"
    by = {o["evidence"]["frame_ids"][0]: o for o in obs}
    assert by["w3_005"]["signature"] == "table.pivot:2col"
    f = await db.frames.find_one({"_id": "w3_005"})
    assert f["label"]["source"] == "nn_copy" and f["steps"][0]["copied_from"] == "f_005"


@pytest.mark.asyncio
async def test_nn_copy_skips_needs_review_labels(env):
    db, _, mp = env
    await db.frames.insert_many(session_frames())
    mp.setattr(lf.llm, "complete", FakeVLM({"f_004": ("table.cast", {}, 0.4)}).complete)
    await interp.interpret_session("u_1", "s_w1_mon")
    await db.frames.insert_many(_week(2))
    fake2 = FakeVLM()
    mp.setattr(lf.llm, "complete", fake2.complete)
    _, st = await interp.interpret_session_detailed("u_1", "s_w2_mon")
    assert st["nn_copied"] == 6 and fake2.calls == [["w2_004"]]   # the unsure frame is asked again


def test_click_target_resolution():
    ocr = {"boxes": [{"text": "Insert", "box": [10, 10, 80, 30]}, {"text": "PivotTable", "box": [100, 10, 200, 30]},
                     {"text": "Insert PivotTable dialog", "box": [0, 0, 400, 300]}]}
    dom = stages.click_target({}, ocr, {"role": "button", "name": "PivotTable"})
    assert dom == {"role": "button", "name": "PivotTable", "box": [100, 10, 200, 30], "source": "dom"}
    pt = stages.click_target({"click": {"x": 150, "y": 20}}, ocr)    # smallest box containing the point
    assert pt["name"] == "PivotTable" and pt["source"] == "ocr"
    assert stages.click_target({"click": {"x": 900, "y": 900}}, ocr) is None
    assert stages.hints({}, ocr, dom)["clicked"] == {"role": "button", "name": "PivotTable"}


@pytest.mark.asyncio
async def test_click_target_from_linked_ui_event(env):
    db, _, mp = env
    await db.frames.insert_many(session_frames())
    await db.ui_events.insert_one({"user_id": "u_1", "kind": "click", "frame_id": "f_005",
                                   "element": {"role": "button", "name": "PivotTable"}})
    fake = FakeVLM()
    mp.setattr(lf.llm, "complete", fake.complete)
    await interp.interpret_session("u_1", "s_w1_mon")
    f5 = await db.frames.find_one({"_id": "f_005"})
    assert f5["click_target"]["source"] == "dom" and f5["click_target"]["name"] == "PivotTable"
    assert f5["click_target"]["box"] is not None                      # found in the frame's OCR
    assert (await db.frames.find_one({"_id": "f_001"}))["click_target"] is None


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
