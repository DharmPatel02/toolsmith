"""Interpreter Stages A + B (local, free / cheap). Plan §6.0.3.

A: perceptual dHash (drop if Hamming <= 6 from the last kept frame of the same window) and
   region diff (drop if < 2 % of pixels changed and the title is unchanged).
B: RapidOCR text + boxes, hints (title, sheet/tab names, headers), secret regex -> drop frame.
"""
from __future__ import annotations

import asyncio
import io
import re
from functools import lru_cache

import imagehash
import numpy as np
from PIL import Image

DHASH_MAX_HAMMING = 6
REGION_DIFF_MIN = 0.02
PIXEL_DELTA = 25          # grey-level change that counts as "changed"
MAX_SIDE = 1280           # keyframes are stored/sent at <= 1280 px

# ---- A: dedupe --------------------------------------------------------------


def open_image(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def dhash(img: Image.Image) -> imagehash.ImageHash:
    return imagehash.dhash(img, hash_size=8)


def region_diff(a: Image.Image, b: Image.Image) -> float:
    """Fraction of pixels whose grey level changed noticeably (both scaled to 320 px wide)."""
    def grey(im):
        w = 320
        return np.asarray(im.convert("L").resize((w, max(1, int(im.height * w / im.width)))), dtype=np.int16)
    ga, gb = grey(a), grey(b)
    if ga.shape != gb.shape:
        return 1.0
    return float((np.abs(ga - gb) > PIXEL_DELTA).mean())


def dedupe(frames: list[dict]) -> tuple[list[dict], list[dict]]:
    """frames: time-ordered, each with `_img` (PIL). Returns (kept, dropped[{frame, reason}])."""
    kept, dropped = [], []
    last_by_window: dict[str, dict] = {}
    last_any: dict | None = None
    for f in frames:
        f["_dhash"] = dhash(f["_img"])
        window = f.get("window_title") or f.get("url_template") or ""
        prev = last_by_window.get(window)
        if prev is not None and (f["_dhash"] - prev["_dhash"]) <= DHASH_MAX_HAMMING:
            dropped.append({"frame": f, "reason": "dhash"})
            continue
        if last_any is not None and (last_any.get("window_title") or "") == (f.get("window_title") or "") \
                and region_diff(last_any["_img"], f["_img"]) < REGION_DIFF_MIN:
            dropped.append({"frame": f, "reason": "region_diff"})
            continue
        kept.append(f)
        last_by_window[window] = f
        last_any = f
    return kept, dropped


def to_webp(img: Image.Image, max_side: int = MAX_SIDE, quality: int = 70) -> bytes:
    im = img.copy()
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=quality)
    return buf.getvalue()


# ---- B: OCR, hints, secrets -------------------------------------------------

@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _ocr_sync(img: Image.Image) -> dict:
    result, _ = _ocr_engine()(np.asarray(img))
    boxes = [{"text": t, "box": [int(v) for pt in (b[0], b[2]) for v in pt], "score": round(float(s), 3)}
             for b, t, s in (result or [])]
    return {"text": "\n".join(b["text"] for b in boxes), "boxes": boxes}


async def ocr(img: Image.Image) -> dict:
    return await asyncio.to_thread(_ocr_sync, img)


SECRET_PATTERNS = [
    re.compile(r"(?i)\b(pass(word|wd)?|api[_ -]?key|secret|token|bearer)\b\s*[:=]\s*\S{4,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),                 # OpenAI-style keys
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                      # AWS access key
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),            # GitHub tokens
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),  # e-mail
]
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def secret_rule(text: str) -> str | None:
    """Name of the first secret rule that matches, else None. A match drops the whole frame."""
    for i, p in enumerate(SECRET_PATTERNS):
        if p.search(text):
            return ["credential", "openai_key", "aws_key", "github_token", "email"][i]
    for m in _CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn(digits):
            return "card_number"
    return None


_SHEET_TAB = re.compile(r"^(Sheet\d+|[A-Z][\w ]{1,20})$")


def hints(frame: dict, ocr_result: dict) -> dict:
    """Cheap context for the VLM: title, app, likely headers / sheet tabs from OCR boxes."""
    boxes = ocr_result.get("boxes", [])
    top = sorted(boxes, key=lambda b: b["box"][1])[:12]
    bottom = sorted(boxes, key=lambda b: -b["box"][3])[:6]
    h = {"window_title": frame.get("window_title"), "app": frame.get("app"), "url": frame.get("url_template"),
         "top_text": [b["text"] for b in top],
         "sheet_tabs": [b["text"] for b in bottom if _SHEET_TAB.match(b["text"])]}
    return {k: v for k, v in h.items() if v}
