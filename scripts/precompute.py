"""P2.3.4: warm every model call the demo makes, so the demo hits the cache.

1. UC1 forge (+ gate + TOOL.md refresh)          -> LLM disk cache (LLM_CACHE_DIR)
2. UC3 heal on the mock-site v2 page              -> LLM disk cache
3. VLM labels for the 3 UC1 recordings            -> data/recordings/labels/s_wN_mon.json (dHash-matched,
                                                     so they survive re-ingest with new frame ids)

By default it runs on a throw-away in-memory DB (nothing touches Atlas); only the cache files
matter. With --atlas it uses MONGODB_URI and the real pattern (so the forge prompt matches the
mined pattern byte for byte), e.g. after P1's seed: --atlas --pattern-id pat_uc1.

    python scripts/precompute.py [--only forge,heal,labels] [--verify] [--relabel]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

A = "data/artifacts/uc1"
KEYFRAMES = ROOT / "data" / "recordings" / "uc1" / "keyframes"
PATTERN_UC1 = {  # fixtures/pattern_uc1.json (TASKS §3.6), used when the fixture file isn't present
    "_id": "pat_uc1", "user_id": "u_1", "status": "proposed",
    "title": "Weekly sales dashboard from Monday xlsx",
    "signature": ["file.open:xlsx", "table.rename:cols", "table.dropna", "table.cast", "table.pivot:2col",
                  "chart.bar", "export.html"],
    "static_steps": {"rename_map": {"reg": "Region", "amt": "Amount"},
                     "pivot": {"index": "Region", "values": "Amount", "aggfunc": "sum"}},
    "dynamic_params": [{"name": "file", "type": "file"}, {"name": "week", "type": "string"}],
    "support": 3, "distinct_days": 3, "variance": 0.08, "periodicity": 0.9, "burstiness": 0.1,
    "avg_minutes": 9, "avg_tokens": 18000, "value": 22.4,
    "evidence_session_ids": ["s_w1_mon", "s_w2_mon", "s_w3_mon"],
}


def log(msg: str) -> None:
    print(msg, flush=True)


async def setup_db(atlas: bool):
    from app.forge import deps
    from app.trust import promote

    if atlas:
        return deps.get_db()
    from mongomock_motor import AsyncMongoMockClient

    db = AsyncMongoMockClient()["precompute"]
    deps.use_db(db)

    async def sequential(db_, ops):  # mongomock has no transactions; this DB is thrown away
        for op in ops:
            await promote.apply_op(db_, op)
    promote._run_in_transaction = sequential
    for w in (1, 2, 3):
        await db.sessions.insert_one({"_id": f"s_w{w}_mon", "user_id": "u_1", "artifacts": {
            "inputs": [f"{A}/week{w}.xlsx"],
            "outputs": [f"{A}/expected/week{w}_pivot.csv", f"{A}/expected/week{w}_chart.json"]}})
    return db


def load_pattern() -> dict:
    p = ROOT / "fixtures" / "pattern_uc1.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else dict(PATTERN_UC1)


async def forge_uc1(db, pattern_id: str | None) -> dict:
    from app.forge.jobs import gate_with_repairs
    from app.forge.service import forge_from_pattern_doc

    pattern = (await db.patterns.find_one({"_id": pattern_id})) if pattern_id else None
    pattern = pattern or load_pattern()
    if not pattern_id:
        await db.patterns.replace_one({"_id": pattern["_id"]}, pattern, upsert=True)
    t0 = time.monotonic()
    cid = await forge_from_pattern_doc(pattern)
    forge_s = time.monotonic() - t0
    gate = await gate_with_repairs(cid)
    cand = await db.candidates.find_one({"_id": cid})
    cost = cand.get("cost") or {}
    return {"step": "forge UC1", "candidate": cid, "status": gate["status"], "forge_s": round(forge_s, 2),
            "total_s": round(time.monotonic() - t0, 2), "calls": cost.get("calls"),
            "cached_calls": cost.get("cached_calls"), "usd": cost.get("usd")}


async def heal_uc3(db) -> dict:
    from app.trust import drift, heal, uc3_seed

    await uc3_seed.seed_uc3_tool("u_1")
    now = datetime.now(UTC)
    await db.runs.insert_many([{"_id": f"run_pre_fail_{i}", "tool_id": uc3_seed.TOOL_ID, "user_id": "u_1",
                                "params": {"url": uc3_seed.shop_url()}, "outcome": "failed", "ok": False,
                                "started_at": now + timedelta(seconds=i)} for i in range(3)])
    await drift.check_drift(uc3_seed.TOOL_ID)
    job = await db.jobs.find_one({"type": "heal", "payload.tool_id": uc3_seed.TOOL_ID})
    t0 = time.monotonic()
    out = await heal.heal_tool(uc3_seed.TOOL_ID, detected_at=job["payload"]["detected_at"],
                               failing_run_ids=job["payload"]["failing_run_ids"])
    cost = out.get("cost") or {}
    return {"step": "heal UC3", "status": out["status"], "page": out.get("page_source"),
            "total_s": round(time.monotonic() - t0, 2), "calls": cost.get("calls"),
            "cached_calls": cost.get("cached_calls"), "usd": cost.get("usd"),
            "diagnosis": (out.get("diagnosis") or out.get("reason") or "")[:90]}


async def label_videos(db, relabel: bool) -> list[dict]:
    from app.interpreter import service as interp
    from scripts.video_to_frames import last_mondays

    sessions = sorted(d for d in KEYFRAMES.glob("s_w*_mon") if d.is_dir()) if KEYFRAMES.exists() else []
    if not sessions:
        return [{"step": "labels", "status": f"skipped: no keyframes in {KEYFRAMES} "
                                            "(run scripts/video_to_frames.py --uc1 data/recordings/uc1 first)"}]
    mondays = last_mondays(len(sessions))
    rows = []
    for sdir, monday in zip(sessions, mondays):
        sid = sdir.name
        target = interp.labels_dir() / f"{sid}.json"
        if target.exists() and not relabel:
            rows.append({"step": f"labels {sid}", "status": "exists (use --relabel)"})
            continue
        if target.exists():
            target.unlink()  # else the interpreter would read it instead of calling the VLM
        start = monday.replace(hour=9)
        frames = [{"_id": f"{sid}_{i:05d}", "user_id": "u_1", "session_id": sid, "source": "video_replay",
                   "app": "excel", "window_title": f"sales_w{sid[3]}.xlsx - Excel", "trigger": "video_replay",
                   "ts": start + timedelta(seconds=5 * i), "image": p.read_bytes()}
                  for i, p in enumerate(sorted(sdir.glob("*.webp")))]
        await db.frames.delete_many({"session_id": sid})
        await db.frames.insert_many(frames)
        t0 = time.monotonic()
        obs, stats = await interp.interpret_session_detailed("u_1", sid)
        docs = [d async for d in db.frames.find({"session_id": sid, "steps.0": {"$exists": True}}).sort("ts", 1)]
        path = interp.export_labels(sid, docs)
        rows.append({"step": f"labels {sid}", "status": f"{len(obs)} steps -> {path}",
                     "total_s": round(time.monotonic() - t0, 2), "calls": stats["vlm_calls"], "usd": stats["usd"],
                     "sequence": " > ".join(o["signature"] for o in obs)[:120]})
    return rows


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="forge,heal,labels")
    ap.add_argument("--atlas", action="store_true", help="use MONGODB_URI instead of an in-memory DB")
    ap.add_argument("--pattern-id", help="with --atlas: forge from this mined pattern")
    ap.add_argument("--verify", action="store_true", help="rerun the forge; must be cached and < 5 s")
    ap.add_argument("--relabel", action="store_true", help="re-run the VLM even if label files exist")
    args = ap.parse_args()
    os.chdir(ROOT)
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    os.environ.setdefault("LLM_CACHE_DIR", str(ROOT / ".cache" / "llm"))
    if os.getenv("LLM_CACHE", "on").lower() == "off":
        log("LLM_CACHE=off: nothing would be cached; unset it")
        return 1

    db = await setup_db(args.atlas)
    steps = set(args.only.split(","))
    rows: list[dict] = []
    for name, fn in (("forge", lambda: forge_uc1(db, args.pattern_id)), ("heal", lambda: heal_uc3(db)),
                     ("labels", lambda: label_videos(db, args.relabel))):
        if name not in steps:
            continue
        log(f"… {name}")
        try:
            out = await fn()
            rows += out if isinstance(out, list) else [out]
        except Exception as e:  # noqa: BLE001 - report and continue with the next step
            rows.append({"step": name, "status": f"FAILED: {type(e).__name__}: {str(e)[:200]}"})

    if args.verify and "forge" in steps:
        again = await forge_uc1(db, args.pattern_id)
        again["step"] = "forge UC1 (verify)"
        ok = again["forge_s"] < 5 and again["calls"] == again["cached_calls"]
        again["status"] += " · cache OK" if ok else " · CACHE MISS"
        rows.append(again)

    log("")
    for r in rows:
        log(" | ".join(f"{k}={v}" for k, v in r.items() if v is not None))
    log(f"\ncache: {os.environ['LLM_CACHE_DIR']}")
    bad = [r for r in rows if any(w in str(r.get("status")).lower() for w in ("failed", "miss"))]
    if bad:
        log(f"{len(bad)} step(s) failed: the demo would call the model live for them")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
