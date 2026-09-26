"""Concierge write actions: submit_feedback and approve_change (plan §6.4, M4).

P1 owns feedback -> policy learning and the policy change log. These prefer P1's functions when they
exist and otherwise write the plan §9 shapes directly, so the chat works before P1's routes land.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.forge import deps

DECISIONS = {"approve", "reject", "edit", "snooze", "ignore", "failed_run"}


async def submit_feedback(
    user_id: str,
    *,
    tool_id: str | None = None,
    pattern_id: str | None = None,
    decision: str = "edit",
    reason: str = "",
    diff: str = "",
) -> dict:
    """feedback: {user_id, pattern_id|tool_id, decision, reason, diff, ts} (plan §9)."""
    if not (tool_id or pattern_id):
        return {"error": "say which tool or suggestion the feedback is about"}
    if decision not in DECISIONS:
        decision = "edit"
    try:
        from app.policy.service import record_feedback  # P1, when it lands
    except ImportError:
        pass
    else:
        return await record_feedback(
            user_id,
            tool_id=tool_id,
            pattern_id=pattern_id,
            decision=decision,
            reason=reason,
            diff=diff,
        )
    doc = {
        "user_id": user_id,
        "decision": decision,
        "reason": reason,
        "diff": diff,
        "ts": datetime.now(UTC),
        "source": "concierge",
        **({"tool_id": tool_id} if tool_id else {}),
        **({"pattern_id": pattern_id} if pattern_id else {}),
    }
    res = await deps.get_db().feedback.insert_one(doc)
    return {"ok": True, "feedback_id": str(res.inserted_id), "decision": decision}


async def approve_change(user_id: str, change_id: str) -> dict:
    """Approve a pending (loosening) policy change: apply its value and mark it applied."""
    try:
        from app.policy.service import approve_change as p1_approve  # P1, when it lands
    except ImportError:
        pass
    else:
        try:
            change = await p1_approve(user_id, change_id)
        except (LookupError, ValueError) as exc:
            return {"error": str(exc)}
        row = (
            change.model_dump(mode="json", by_alias=True)
            if hasattr(change, "model_dump")
            else dict(change)
        )
        return {
            "ok": True,
            "field": row.get("field"),
            "value": row.get("to"),
            "status": row.get("status"),
        }
    db = deps.get_db()
    policy = await db.policy.find_one({"_id": f"policy:{user_id}"})
    change = next(
        (c for c in (policy or {}).get("changes", []) if c.get("id", c.get("_id")) == change_id),
        None,
    )
    if change is None:
        return {"error": f"no policy change {change_id}"}
    if change.get("status") != "pending":
        return {"ok": True, "already": change.get("status")}
    key = "id" if "id" in change else "_id"
    new_value = change.get("to", change.get("new"))
    field = (
        change["field"]
        if change["field"].startswith("thresholds.")
        else f"thresholds.{change['field']}"
    )
    await db.policy.update_one(
        {"_id": f"policy:{user_id}", f"changes.{key}": change_id},
        {
            "$set": {
                field: new_value,
                "changes.$.status": "applied",
                "changes.$.approved_at": datetime.now(UTC),
            },
            "$inc": {"version": 1},
        },
    )
    await deps.publish(
        user_id,
        "policy_changed",
        {**{k: v for k, v in change.items() if k != "ts"}, "status": "applied", "approved": True},
    )
    return {"ok": True, "field": field, "value": new_value}
