"""VLM frame labeling (P2.1.9). Used by the interpreter, Stage C.

Call `label_frames(frames, vocab)` with 6-10 keyframes of one segment. It builds one
vision call, then enforces the contract in TASKS §3.3:
  - every step cites a frame_id that was actually sent (others are dropped)
  - verb is in the vocab, else it becomes "other" and keeps `proposed_verb`
  - confidence < VLM_MIN_CONFIDENCE (0.6) -> needs_review: true
"""
from __future__ import annotations

import json

from app import llm

VLM_MIN_CONFIDENCE = 0.6

LABEL_FRAMES_PROMPT = """\
You label screenshots of a person working on a computer, to find the steps of a repeated workflow.

You get a short ordered sequence of keyframes from ONE work session. Each frame has an id,
a timestamp, the window title/app, and OCR text read from the screen. Describe the user
ACTIONS that the frames show, in order. One step = one meaningful action (open a file,
rename columns, drop empty rows, change a type, make a pivot table, insert a chart,
export/save, navigate to a page, submit a form, ...). Ignore scrolling, hovering and idle frames.

Rules:
1. Every step MUST cite the frame_id where its effect is visible. Only use the ids given.
2. `verb` MUST be one of the ALLOWED VERBS below. If nothing fits, use "other" and put your
   own suggestion in `proposed_verb` as "domain.verb" (lowercase, e.g. "table.sort").
3. `args_shape` describes the SHAPE of the arguments, never personal data: file extension,
   which column names are rows/values, number of columns, chart type. Column headers and
   sheet names are fine; cell values, emails, names of people, numbers from cells are not.
4. `target` is what the action was applied to: {"kind": "file|range|sheet|chart|page|form|element",
   "name": short name as shown on screen}.
5. `confidence` in [0, 1]: how sure you are this step happened as described. If you are guessing,
   say so with a low value (< 0.6) instead of inventing detail.
6. Do not repeat the same step for consecutive frames showing the same state.
Return JSON only: {"steps": [...]}.
"""

LABEL_FRAMES_SCHEMA: dict = {
    "type": "object",
    "required": ["steps"],
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["frame_id", "app", "verb", "target", "args_shape", "confidence"],
                "properties": {
                    "frame_id": {"type": "string"},
                    "app": {"type": "string"},
                    "verb": {"type": "string"},
                    "proposed_verb": {"type": "string"},
                    "target": {
                        "type": "object",
                        "properties": {"kind": {"type": "string"}, "name": {"type": "string"}},
                    },
                    "args_shape": {"type": "object"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        }
    },
}


def build_messages(frames: list[dict], vocab: list[str]) -> list[dict]:
    """frames: [{frame_id, image_bytes, mime?, ts?, app?, window_title?, url_template?,
    ocr_text?, hints?: dict}] in time order."""
    content: list[dict] = [{"type": "text", "text": "ALLOWED VERBS: " + ", ".join(sorted(vocab))}]
    for f in frames:
        meta = {k: f[k] for k in ("frame_id", "ts", "app", "window_title", "url_template") if f.get(k)}
        if f.get("hints"):
            meta["hints"] = f["hints"]
        ocr = (f.get("ocr_text") or "")[:1500]
        content.append({"type": "text", "text": f"FRAME {json.dumps(meta, default=str)}\nOCR: {ocr}"})
        content.append(llm.image_part(f["image_bytes"], f.get("mime", "image/webp")))
    return [{"role": "system", "content": LABEL_FRAMES_PROMPT}, {"role": "user", "content": content}]


def enforce_contract(steps: list[dict], frame_ids: set[str], vocab: set[str]) -> list[dict]:
    out = []
    for s in steps:
        if s.get("frame_id") not in frame_ids:
            continue
        s = dict(s)
        verb = (s.get("verb") or "").strip().lower()
        if verb not in vocab:
            s["proposed_verb"] = s.get("proposed_verb") or (verb if verb and verb != "other" else None)
            verb = "other"
        s["verb"] = verb
        s["confidence"] = float(s.get("confidence") or 0.0)
        s["needs_review"] = s["confidence"] < VLM_MIN_CONFIDENCE
        out.append(s)
    return out


async def label_frames(frames: list[dict], vocab: list[str]) -> tuple[list[dict], llm.LLMResult]:
    """One VLM call over a segment. Returns (contract-clean steps, raw LLMResult for cost)."""
    if not frames:
        return [], llm.LLMResult(text="")
    res = await llm.complete("vision", build_messages(frames, vocab), LABEL_FRAMES_SCHEMA, max_tokens=2048)
    steps = enforce_contract(res.json.get("steps", []), {f["frame_id"] for f in frames}, set(vocab))
    return steps, res
