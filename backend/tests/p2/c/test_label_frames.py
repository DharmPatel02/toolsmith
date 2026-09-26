"""P2.1.9: 3 sample frames -> valid JSON, frame_id on every step, contract enforced."""
import io
import os

import pytest
from dotenv import load_dotenv
from PIL import Image, ImageDraw

from app import llm
from app.prompts import label_frames as lf

load_dotenv()
VOCAB = ["file.open", "table.rename", "table.dropna", "table.pivot", "chart.bar", "export.html"]


def _frame(fid, text):
    img = Image.new("RGB", (640, 360), "white")
    ImageDraw.Draw(img).text((20, 20), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, "WEBP")
    return {"frame_id": fid, "image_bytes": buf.getvalue(), "app": "excel",
            "window_title": "sales_w1.xlsx - Excel", "ocr_text": text}


FRAMES = [_frame("f_1", "File > Open sales_w1.xlsx"),
          _frame("f_2", "Insert PivotTable  Rows: Region  Values: Sum of Amount"),
          _frame("f_3", "Insert Chart: Clustered Bar")]


def test_enforce_contract():
    steps = [
        {"frame_id": "f_1", "verb": "file.open", "confidence": 0.9},
        {"frame_id": "f_9", "verb": "file.open", "confidence": 0.9},        # unknown frame -> dropped
        {"frame_id": "f_2", "verb": "table.sort", "confidence": 0.8},       # not in vocab -> other
        {"frame_id": "f_3", "verb": "chart.bar", "confidence": 0.4},        # low -> needs_review
    ]
    out = lf.enforce_contract(steps, {"f_1", "f_2", "f_3"}, set(VOCAB))
    assert [s["frame_id"] for s in out] == ["f_1", "f_2", "f_3"]
    assert out[1]["verb"] == "other" and out[1]["proposed_verb"] == "table.sort"
    assert [s["needs_review"] for s in out] == [False, False, True]


def test_messages_carry_every_frame():
    msgs = lf.build_messages(FRAMES, VOCAB)
    parts = msgs[1]["content"]
    assert sum(p["type"] == "image_url" for p in parts) == 3
    assert "table.pivot" in parts[0]["text"]


@pytest.mark.asyncio
async def test_label_frames_mocked(monkeypatch):
    async def fake_complete(tier, messages, schema, **kw):
        assert tier == "vision"
        return llm.LLMResult(text="", json={"steps": [
            {"frame_id": "f_1", "app": "excel", "verb": "file.open", "target": {"kind": "file", "name": "sales_w1.xlsx"},
             "args_shape": {"ext": "xlsx"}, "confidence": 0.95}]})
    monkeypatch.setattr(lf.llm, "complete", fake_complete)
    steps, _ = await lf.label_frames(FRAMES, VOCAB)
    assert steps[0]["verb"] == "file.open" and steps[0]["needs_review"] is False


@pytest.mark.skipif(not os.getenv("LLM_VISION_MODEL"), reason="no LLM_VISION_MODEL in .env")
@pytest.mark.asyncio
async def test_label_frames_live():
    steps, _ = await lf.label_frames(FRAMES, VOCAB)
    assert steps and all(s["frame_id"] in {"f_1", "f_2", "f_3"} for s in steps)
    assert "table.pivot" in [s["verb"] for s in steps]
