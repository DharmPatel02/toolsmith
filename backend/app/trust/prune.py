"""Prune (P2.3.3): idle or failing tools -> `deprecated`, unless an active tool depends on them.

Below `policy.thresholds.prune.min_runs_30d` runs in 30 days, or below `min_success_rate`,
a tool is deprecated. Prune safety: if `dependents()` returns active tools, it is kept and the
reason is published (the policy strip shows "kept: Y depends on it"). Tools younger than
GRACE_DAYS are skipped: a tool promoted minutes ago has no runs yet and isn't idle.
Publishes one `pruned` event per pass.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.forge import deps
from app.trust.drift import run_ok

WINDOW_DAYS = 30
GRACE_DAYS = 7
DEFAULTS = {"min_runs_30d": 2, "min_success_rate": 0.6}


def _aware(dt):
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


async def prune(user_id: str) -> dict:
    db = deps.get_db()
    pol = await db.policy.find_one({"_id": f"policy:{user_id}"}) or {}
    th = {**DEFAULTS, **(((pol.get("thresholds") or {}).get("prune")) or {})}
    now = datetime.now(UTC)
    since = now - timedelta(days=WINDOW_DAYS)
    pruned, kept = [], []
    tools = [t async for t in db.tools.find({"user_id": user_id, "status": "active"})]
    for tool in tools:
        created = _aware(tool.get("created_at"))
        if created and created > now - timedelta(days=GRACE_DAYS):
            continue
        results = [ok for r in [r async for r in db.runs.find({"tool_id": tool["_id"]})]
                   if (_aware(r.get("started_at")) or now) >= since and (ok := run_ok(r)) is not None]
        n = len(results)
        rate = sum(results) / n if n else None
        if n < th["min_runs_30d"]:
            reason = f"{n} runs in {WINDOW_DAYS} days < {th['min_runs_30d']}"
        elif rate < th["min_success_rate"]:
            reason = f"success rate {rate:.0%} < {th['min_success_rate']:.0%}"
        else:
            continue
        item = {"tool_id": tool["_id"], "name": tool.get("name"), "reason": reason}
        users = await deps.dependents(user_id, tool["_id"])
        if users:
            names = [t.get("name", t["_id"]) async for t in db.tools.find({"_id": {"$in": users}}, {"name": 1})]
            kept.append({**item, "kept_because": f"kept: {', '.join(names)} depend{'s' if len(names) == 1 else ''} on it",
                         "dependents": users})
            continue
        await db.tools.update_one({"_id": tool["_id"], "status": "active"},
                                  {"$set": {"status": "deprecated", "deprecated_at": now, "deprecated_reason": reason}})
        pruned.append(item)
    count = await db.tools.count_documents({"user_id": user_id, "status": "active"})
    result = {"pruned": pruned, "kept": kept, "toolbox_count": count}
    await deps.publish(user_id, "pruned", result)
    return result
