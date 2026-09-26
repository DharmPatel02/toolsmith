"""Trust ladder updates (P2.2.4).

Promote creates tools at ``dry_run``. This module only advances to ``supervised``
or proposes ``autonomous``; user approval of the proposal belongs elsewhere.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.forge import deps


DRY_RUN = "dry_run"
SUPERVISED = "supervised"
AUTONOMOUS = "autonomous"
DEFAULT_SUCCESS_STREAK_THRESHOLD = 8
DEFAULT_MAX_EDIT_RATE = 0.1
PREVIEW_CONFIRMS_TO_SUPERVISED = 3
EDIT_RATE_WINDOW = 10


async def update_after_run(run: dict) -> None:
    db = deps.get_db()
    tool_id = run.get("tool_id")
    user_id = run.get("user_id")
    if not tool_id or not user_id:
        raise ValueError("run must include tool_id and user_id")

    tool = await db.tools.find_one({"_id": tool_id, "user_id": user_id})
    if not tool:
        raise ValueError(f"tool {tool_id} not found for {user_id}")

    policy = await _policy(db, user_id)
    before = tool.get("trust", DRY_RUN)
    after = before
    history = [*tool.get("trust_history", []), _history_event(run)]
    trust_streak = int(tool.get("trust_streak", 0) or 0)
    preview_confirms = int(tool.get("preview_confirms", 0) or 0)
    proposal = tool.get("trust_proposal")
    outcome = run.get("outcome")
    rejected = bool(run.get("user_rejected")) or run.get("user_confirmed") is False

    if outcome == "failed" or rejected:
        trust_streak = 0
        preview_confirms = 0
        proposal = None
        after = _demote(before)
    elif before == DRY_RUN:
        trust_streak = 0
        if outcome == "success" and run.get("user_confirmed") is True:
            preview_confirms += 1
            if preview_confirms >= PREVIEW_CONFIRMS_TO_SUPERVISED:
                after = SUPERVISED
                preview_confirms = 0
        else:
            preview_confirms = 0
    elif before == SUPERVISED:
        if outcome == "success":
            trust_streak += 1
        elif outcome == "edited":
            trust_streak = 0
        if trust_streak >= policy["success_streak_threshold"] and _edit_rate(history) <= policy["max_edit_rate"]:
            proposal = {
                "to": AUTONOMOUS,
                "because": (
                    f"{trust_streak} successful runs with edit rate "
                    f"{_edit_rate(history):.2f} <= {policy['max_edit_rate']:.2f}"
                ),
                "created_at": datetime.now(UTC),
            }
    elif before == AUTONOMOUS:
        trust_streak = trust_streak + 1 if outcome == "success" else 0

    update = {
        "trust": after,
        "trust_streak": trust_streak,
        "preview_confirms": preview_confirms,
        "trust_history": history[-50:],
        "updated_at": datetime.now(UTC),
    }
    if proposal is None:
        update["trust_proposal"] = None
    else:
        update["trust_proposal"] = proposal

    await db.tools.update_one({"_id": tool_id, "user_id": user_id}, {"$set": update})
    if after != before:
        await deps.publish(user_id, "trust_changed", {"tool_id": tool_id, "from": before, "to": after})


async def _policy(db: Any, user_id: str) -> dict[str, float | int]:
    doc = await db.policy.find_one({"_id": f"policy:{user_id}"}) or {}
    return {
        "success_streak_threshold": int(
            doc.get("success_streak_threshold")
            or doc.get("trust_success_streak")
            or DEFAULT_SUCCESS_STREAK_THRESHOLD
        ),
        "max_edit_rate": float(doc.get("max_edit_rate", DEFAULT_MAX_EDIT_RATE)),
    }


def _history_event(run: dict) -> dict:
    return {
        "run_id": run.get("_id") or run.get("run_id"),
        "outcome": run.get("outcome"),
        "mode": run.get("mode"),
        "user_confirmed": run.get("user_confirmed"),
        "created_at": datetime.now(UTC),
    }


def _demote(level: str) -> str:
    if level == AUTONOMOUS:
        return SUPERVISED
    if level == SUPERVISED:
        return DRY_RUN
    return DRY_RUN


def _edit_rate(history: list[dict]) -> float:
    window = [h for h in history if h.get("outcome") in {"success", "failed", "edited"}][-EDIT_RATE_WINDOW:]
    if not window:
        return 0.0
    return sum(1 for h in window if h.get("outcome") == "edited") / len(window)
