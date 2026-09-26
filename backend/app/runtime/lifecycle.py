"""Cancel a tool (plan §1.4): soft delete, re-suggest later, or never again.

Delete is blocked while the tool is in use (a run awaits approval) or another active tool depends on
it. Otherwise the tool leaves the shop (`status: deleted`; versions, runs and audit stay) and its
pattern goes back to `mined` with a cooldown, so ToolSmith may suggest it again if the user keeps
doing the work by hand. "Don't suggest again" adds a policy rule instead.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import get_db
from app.runtime.lineage import dependents

DEFAULT_RESUGGEST_MINUTES = 7 * 24 * 60


async def delete_tool(user_id: str, tool_id: str, *, never_suggest_again: bool = False) -> dict:
    db = get_db()
    tool = await db.tools.find_one(
        {"$or": [{"_id": tool_id}, {"tool_id": tool_id}], "user_id": user_id}
    )
    if not tool or tool.get("status") == "deleted":
        raise LookupError("Unknown tool")
    identity = str(tool.get("tool_id") or tool["_id"])
    waiting = await db.runs.count_documents(
        {"user_id": user_id, "tool_id": identity, "status": "awaiting_approval"}
    )
    if waiting:
        return {"ok": False, "blocked_reason": f"{waiting} run(s) are waiting for approval"}
    users = await dependents(user_id, identity)
    if users:
        return {"ok": False, "blocked_reason": f"{', '.join(users)} depend(s) on it"}

    now = datetime.now(timezone.utc)
    await db.tools.update_one(
        {"_id": tool["_id"]}, {"$set": {"status": "deleted", "deleted_at": now}}
    )
    pattern = await db.patterns.find_one({"tool_id": identity, "user_id": user_id})
    if pattern:
        if never_suggest_again:
            await db.patterns.update_one(
                {"_id": pattern["_id"]},
                {
                    "$set": {
                        "status": "declined",
                        "declined_reason": "deleted: don't suggest again",
                        "deleted_at": now,
                        "deleted_tool_id": identity,
                    }
                },
            )
            await db.policy.update_one(
                {"_id": f"policy:{user_id}"},
                {
                    "$push": {
                        "rules": {
                            "kind": "never",
                            "pattern_id": pattern["_id"],
                            "because": f"deleted {tool.get('name', identity)}",
                            "created_at": now,
                        }
                    }
                },
                upsert=True,
            )
        else:
            policy = await db.policy.find_one({"_id": f"policy:{user_id}"}) or {}
            minutes = float(
                (policy.get("thresholds") or {}).get(
                    "resuggest_after_delete_minutes", DEFAULT_RESUGGEST_MINUTES
                )
            )
            await db.patterns.update_one(
                {"_id": pattern["_id"]},
                {
                    "$set": {
                        "status": "mined",
                        "deleted_at": now,
                        "deleted_tool_id": identity,
                        "cooldown_until": now + timedelta(minutes=minutes),
                    },
                    "$unset": {"tool_id": ""},
                },
            )
    return {"ok": True, "tool_id": identity, "never_suggest_again": never_suggest_again}
