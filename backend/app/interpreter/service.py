"""Interpreter (P2.2.6): frames of one session -> labeled, canonical T2 steps.

A dedupe (dHash + region diff) -> B OCR + hints + secret drop -> C multimodal embedding +
batched VLM labels (label_frames) -> D action_vocab + canonical signatures.

Writes back to `frames` (ocr, dhash, embedding, label, steps, interp) and returns T2
observations for P1's fusion (§3.5b: structured steps win, frames become evidence).
Publishes `frame_labeled` per labeled step.

Hand-label fallback (TASKS P2.2.6, 13:45): if `<INTERPRETER_LABELS_DIR>/<session_id>.json`
exists ({"steps": [...]} in the §3.3 VLM shape), it replaces the VLM call (label source "hand").
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from app import embeddings
from app.forge import deps
from app.forge.spec import REPO_ROOT
from app.interpreter import stages, vocab
from app.prompts.label_frames import enforce_contract, label_frames

log = logging.getLogger(__name__)
VLM_BATCH = 8            # 6-10 frames per call (§3.5b)
VLM_CONCURRENCY = 3


async def interpret_session(user_id: str, session_id: str) -> list[dict]:
    obs, _ = await interpret_session_detailed(user_id, session_id)
    return obs


async def interpret_session_detailed(user_id: str, session_id: str) -> tuple[list[dict], dict]:
    db = deps.get_db()
    docs = [d async for d in db.frames.find({"user_id": user_id, "session_id": session_id,
                                             "interp": {"$exists": False}}).sort("ts", 1)]
    stats = {"frames": len(docs), "kept": 0, "dropped": {}, "labeled_steps": 0, "needs_review": 0,
             "vlm_calls": 0, "usd": 0.0, "label_source": None}
    if not docs:
        return [], stats

    frames = []
    for d in docs:
        data = await load_image(d)
        if data is None:
            await _mark(d, kept=False, reason="no_image")
            _count(stats, "no_image")
            continue
        frames.append({**d, "_id": str(d["_id"]), "_img": stages.open_image(data)})

    # A — dedupe
    kept, dropped = stages.dedupe(frames)
    for x in dropped:
        await _mark(x["frame"], kept=False, reason=x["reason"], dhash=str(x["frame"]["_dhash"]))
        _count(stats, x["reason"])

    # B — OCR, secrets, hints
    clean = []
    for f in kept:
        f["_ocr"] = await stages.ocr(f["_img"])
        text = "\n".join(filter(None, [f["_ocr"]["text"], f.get("window_title"), f.get("url_template")]))
        if rule := stages.secret_rule(text):
            await drop_secret_frame(f, rule)
            _count(stats, f"secret_{rule}")
            continue
        f["_hints"] = stages.hints(f, f["_ocr"])
        f["_webp"] = stages.to_webp(f["_img"])
        clean.append(f)
    stats["kept"] = len(clean)
    if not clean:
        return [], stats

    # C — multimodal embeddings + labels
    vecs = await embeddings.embed_multimodal([{"image_bytes": f["_webp"], "text": f["_ocr"]["text"][:2000]}
                                              for f in clean])
    voc = await vocab.load_vocab()
    verbs = vocab.active_verbs(voc)
    steps, source, usage = await _label(session_id, clean, verbs)
    stats.update(label_source=source, vlm_calls=len(usage), usd=round(sum(u.usd for u in usage), 6))

    # D — vocab + canonical signatures
    steps = await vocab.canonicalize(steps, voc)
    for s in steps:
        s["signature"] = vocab.signature(s["verb"], s.get("args_shape") or {})
        s["label_source"] = source

    by_frame: dict[str, list[dict]] = {}
    for s in steps:
        by_frame.setdefault(s["frame_id"], []).append(s)
    model = embeddings.mm_model()
    observations = []
    for f, vec in zip(clean, vecs, strict=True):
        fsteps = by_frame.get(f["_id"], [])
        label = max(fsteps, key=lambda s: s["confidence"]) if fsteps else None
        await _mark(f, kept=True, dhash=str(f["_dhash"]), extra={
            "ocr": f["_ocr"], "embedding": vec, "embedding_model": model, "steps": fsteps,
            "label": {"verb": label["verb"], "signature": label["signature"], "args_shape": label.get("args_shape"),
                      "confidence": label["confidence"], "source": source,
                      "needs_review": label["needs_review"]} if label else None})
        for s in fsteps:
            observations.append(to_observation(user_id, session_id, f, s))
            await deps.publish(user_id, "frame_labeled", {
                "frame_id": f["_id"], "session_id": session_id, "verb": s["verb"], "signature": s["signature"],
                "confidence": s["confidence"], "needs_review": s["needs_review"],
                "thumb_url": f"/frames/{f['_id']}/thumb"})
    stats["labeled_steps"] = len(observations)
    stats["needs_review"] = sum(1 for o in observations if o["needs_review"])
    return observations, stats


async def _label(session_id: str, frames: list[dict], verbs: list[str]):
    """Hand labels if a file exists for the session, else batched VLM calls."""
    hand = hand_labels(session_id)
    ids = {f["_id"] for f in frames}
    if hand is not None:
        return enforce_contract(hand, ids, set(verbs)), "hand", []
    sem = asyncio.Semaphore(VLM_CONCURRENCY)

    async def one(batch):
        async with sem:
            payload = [{"frame_id": f["_id"], "image_bytes": f["_webp"], "ts": f.get("ts"), "app": f.get("app"),
                        "window_title": f.get("window_title"), "url_template": f.get("url_template"),
                        "ocr_text": f["_ocr"]["text"], "hints": f["_hints"]} for f in batch]
            return await label_frames(payload, verbs)

    results = await asyncio.gather(*[one(frames[i:i + VLM_BATCH]) for i in range(0, len(frames), VLM_BATCH)])
    order = {f["_id"]: i for i, f in enumerate(frames)}
    steps = sorted((s for st, _ in results for s in st), key=lambda s: order[s["frame_id"]])
    return steps, "vlm", [u for _, u in results]


def hand_labels(session_id: str) -> list[dict] | None:
    d = Path(os.getenv("INTERPRETER_LABELS_DIR", REPO_ROOT / "data" / "recordings" / "labels"))
    p = d / f"{session_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8")).get("steps", [])


def to_observation(user_id: str, session_id: str, frame: dict, step: dict) -> dict:
    return {
        "ts": frame.get("ts"), "meta": {"user_id": user_id, "source": step.get("app") or frame.get("app") or "screen"},
        "session_id": session_id, "action": step["verb"], "signature": step["signature"],
        "target": step.get("target") or {}, "args_shape": step.get("args_shape") or {},
        "needs_review": step["needs_review"],
        "evidence": {"frame_ids": [frame["_id"]], "ocr_snippet": frame["_ocr"]["text"][:200], "tier": "T2",
                     "confidence": step["confidence"]},
    }


# ---- frame IO ------------------------------------------------------------------

async def load_image(frame: dict) -> bytes | None:
    """Keyframe bytes from GridFS `keyframes`; falls back to the inline thumbnail."""
    if frame.get("gridfs_id") is not None:
        try:
            from motor.motor_asyncio import AsyncIOMotorGridFSBucket

            stream = await AsyncIOMotorGridFSBucket(deps.get_db(), "keyframes").open_download_stream(frame["gridfs_id"])
            return await stream.read()
        except Exception as e:  # noqa: BLE001 - a missing file shouldn't kill the session
            log.warning("keyframe %s unreadable: %s", frame.get("_id"), e)
    thumb = frame.get("image") or frame.get("thumb")
    return bytes(thumb) if thumb else None


async def drop_secret_frame(frame: dict, rule: str) -> None:
    """Drop, don't blur (§6.0.6): delete the frame doc and its keyframe, count it in the audit."""
    db = deps.get_db()
    if frame.get("gridfs_id") is not None:
        try:
            from motor.motor_asyncio import AsyncIOMotorGridFSBucket

            await AsyncIOMotorGridFSBucket(db, "keyframes").delete(frame["gridfs_id"])
        except Exception as e:  # noqa: BLE001
            log.warning("could not delete keyframe for %s: %s", frame["_id"], e)
    await db.frames.delete_one({"_id": frame["_id"]})
    if frame.get("capture_session_id"):
        await db.capture_sessions.update_one({"_id": frame["capture_session_id"]},
                                             {"$inc": {f"frames_dropped_by_rule.secret_{rule}": 1,
                                                       "frames_kept": -1}})


async def _mark(frame: dict, kept: bool, reason: str | None = None, dhash: str | None = None,
                extra: dict | None = None) -> None:
    upd = {"interp": {"kept": kept, "reason": reason, "at": datetime.now(UTC)}, **(extra or {})}
    if dhash:
        upd["dhash"] = dhash
    await deps.get_db().frames.update_one({"_id": frame["_id"]}, {"$set": upd})


def _count(stats: dict, key: str) -> None:
    stats["dropped"][key] = stats["dropped"].get(key, 0) + 1
