"""P2.3.5 quick calibration of the runtime router thresholds (T_high / T_low).

Scores each (intent, expected tool) pair with the same `search_tools` the runtime uses, sweeps
thresholds, prints the F1 table and writes the winners to `policy` via `record_change`
(origin "calibration"). Routing: score >= T_high -> found · T_low <= score < T_high -> related ·
below -> not_found.

- T_high maximises F1 of "found AND it is the right tool" (a wrong confident hit is a false positive).
- T_low (<= T_high) maximises F1 of "some tool is worth mentioning" (pair has a tool vs has none).

    python scripts/calibrate.py [--user u_1] [--pairs scripts/calibration_pairs.json] [--dry]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

GRID = [round(0.30 + i * 0.01, 2) for i in range(66)]  # 0.30 .. 0.95


def f1(tp: int, fp: int, fn: int) -> float:
    return 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)


def sweep(scored: list[dict], grid: list[float] = GRID) -> dict:
    """scored: [{expected: tool_id|None, top: tool_id|None, score: float}]."""
    def high_f1(t):
        tp = sum(1 for s in scored if s["expected"] and s["score"] >= t and s["top"] == s["expected"])
        fp = sum(1 for s in scored if s["score"] >= t and s["top"] != s["expected"])
        fn = sum(1 for s in scored if s["expected"] and not (s["score"] >= t and s["top"] == s["expected"]))
        return f1(tp, fp, fn), tp, fp, fn

    def low_f1(t):
        tp = sum(1 for s in scored if s["expected"] and s["score"] >= t)
        fp = sum(1 for s in scored if not s["expected"] and s["score"] >= t)
        fn = sum(1 for s in scored if s["expected"] and s["score"] < t)
        return f1(tp, fp, fn), tp, fp, fn

    table = [{"t": t, "high": high_f1(t), "low": low_f1(t)} for t in grid]
    # ties -> the stricter (higher) threshold for T_high, the middle of the plateau for T_low
    best_high = max(table, key=lambda r: (round(r["high"][0], 6), r["t"]))
    t_high = best_high["t"]
    lows = [r for r in table if r["t"] <= t_high]
    top = max(round(r["low"][0], 6) for r in lows)
    plateau = [r["t"] for r in lows if round(r["low"][0], 6) == top]
    t_low = plateau[len(plateau) // 2]
    return {"T_high": t_high, "T_low": t_low, "f1_high": best_high["high"][0],
            "f1_low": next(r["low"][0] for r in table if r["t"] == t_low), "table": table}


async def resolve_expected(user_id: str, kind: str | None) -> str | None:
    from app.forge import deps
    from app.trust import uc3_seed

    if kind is None:
        return None
    db = deps.get_db()
    if kind == "uc3":
        return uc3_seed.TOOL_ID
    if kind == "uc1":
        pat = await db.patterns.find_one({"_id": "pat_uc1"})
        if pat and pat.get("tool_id"):
            return pat["tool_id"]
        tool = await db.tools.find_one({"user_id": user_id, "name": {"$regex": "sales"}})
        return tool["_id"] if tool else None
    return kind  # a literal tool id


async def score_pairs(user_id: str, pairs: list[dict]) -> list[dict]:
    from app.forge import deps

    out = []
    for p in pairs:
        hits = await deps.search_tools(user_id, p["intent"], 1)
        top = hits[0] if hits else None
        out.append({"intent": p["intent"], "expected": await resolve_expected(user_id, p["tool"]),
                    "top": deps.field(top, "tool_id") if top else None,
                    "score": float(deps.field(top, "score", 0.0) or 0.0) if top else 0.0})
    return out


def print_table(scored: list[dict], result: dict) -> None:
    print(f"{'intent':<62} {'expected':<18} {'top':<18} score")
    for s in scored:
        print(f"{s['intent'][:61]:<62} {str(s['expected']):<18} {str(s['top']):<18} {s['score']:.3f}")
    print(f"\n{'t':>5}  {'F1 found(T_high)':>17}  {'F1 related(T_low)':>18}")
    for r in result["table"][::5]:
        mark = " <- T_high" if r["t"] == result["T_high"] else (" <- T_low" if r["t"] == result["T_low"] else "")
        print(f"{r['t']:>5.2f}  {r['high'][0]:>17.2f}  {r['low'][0]:>18.2f}{mark}")
    print(f"\nT_high = {result['T_high']} (F1 {result['f1_high']:.2f}) · T_low = {result['T_low']} "
          f"(F1 {result['f1_low']:.2f})")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default=os.getenv("DEMO_USER_ID", "u_1"))
    ap.add_argument("--pairs", type=Path, default=ROOT / "scripts" / "calibration_pairs.json")
    ap.add_argument("--dry", action="store_true", help="print only, don't write the policy")
    args = ap.parse_args()
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    from app import embeddings
    from app.forge import deps

    if embeddings.text_model().startswith("fake"):
        print("WARNING: fake embeddings (no VOYAGE_API_KEY): scores are meaningless; not writing the policy.")
        args.dry = True
    pairs = json.loads(args.pairs.read_text(encoding="utf-8"))["pairs"]
    scored = await score_pairs(args.user, pairs)
    if not any(s["expected"] for s in scored):
        print("no expected tools resolved (seed UC3 / promote UC1 first)")
        return 1
    result = sweep(scored)
    print_table(scored, result)
    if args.dry:
        return 0
    pol = await deps.get_db().policy.find_one({"_id": f"policy:{args.user}"}) or {}
    th = pol.get("thresholds") or {}
    because = f"calibration on {len(scored)} pairs: F1 {result['f1_high']:.2f} / {result['f1_low']:.2f}"
    for key in ("T_high", "T_low"):
        old, new = th.get(key), result[key]
        if old == new:
            continue
        direction = "tighten" if old is None or new > old else "loosen"
        await deps.record_change(args.user, f"thresholds.{key}", new, direction, because, ["calibration"])
        print(f"policy thresholds.{key}: {old} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
