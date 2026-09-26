import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config import ROOT, get_settings
from app.contracts import PolicyChange, PolicyDoc
from app.db import get_db
from app.events import publish
from app.fixtures import require_demo_user


def _default_policy(user_id: str) -> dict:
    policy = deepcopy(json.loads((ROOT / "fixtures/policy.json").read_text()))
    policy["_id"] = f"policy:{user_id}"
    return policy


def _lookup(document: dict, field: str):
    value = document
    for key in field.split("."):
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _as_policy_doc(document: dict) -> PolicyDoc:
    allowed = set(PolicyDoc.model_fields)
    allowed.update(
        field.alias for field in PolicyDoc.model_fields.values() if field.alias is not None
    )
    return PolicyDoc(**{key: value for key, value in document.items() if key in allowed})


async def get_policy(user_id: str) -> PolicyDoc:
    if get_settings().stub_mode:
        require_demo_user(user_id)
        return PolicyDoc(**_default_policy(user_id))
    db = get_db()
    default = _default_policy(user_id)
    await db.policy.update_one({"_id": default["_id"]}, {"$setOnInsert": default}, upsert=True)
    return _as_policy_doc(await db.policy.find_one({"_id": default["_id"]}))


async def record_change(
    user_id: str, field: str, new, direction: str, because: str, origin_ids: list[str]
) -> PolicyChange:
    policy = await get_policy(user_id)
    old = _lookup(policy.model_dump(by_alias=True), field)
    change = PolicyChange(
        id=f"change_fixture_{uuid4().hex}",
        field=field,
        old=old,
        new=new,
        direction=direction,
        because=because,
        origin_feedback_ids=origin_ids,
        status="pending" if direction == "loosen" else "applied",
    )
    if get_settings().stub_mode:
        return change

    db = get_db()
    update = {"$push": {"changes": change.model_dump(by_alias=True)}}
    if change.status == "applied":
        update["$set"] = {field: new, "updated_at": datetime.now(timezone.utc)}
    await db.policy.update_one({"_id": policy.id}, update)
    await publish(user_id, "policy_changed", {"change_id": change.id, "field": field})
    return change


async def approve_change(user_id: str, change_id: str) -> PolicyChange:
    """Apply an explicitly approved loosening change and retain its audit record."""
    if get_settings().stub_mode:
        raise LookupError("Fixture policy changes are not persisted")
    db = get_db()
    policy = await get_policy(user_id)
    raw = policy.model_dump(by_alias=True)
    change = next((row for row in raw["changes"] if row["id"] == change_id), None)
    if not change:
        raise LookupError("Unknown policy change")
    if change["status"] == "applied":
        return PolicyChange(**change)
    if change["direction"] != "loosen":
        raise ValueError("Only pending loosening changes require approval")
    await db.policy.update_one(
        {"_id": policy.id, "changes.id": change_id},
        {
            "$set": {
                change["field"]: change["to"],
                "changes.$.status": "applied",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    change["status"] = "applied"
    await publish(user_id, "policy_changed", {"change_id": change_id, "field": change["field"]})
    return PolicyChange(**change)


async def learn_policy(user_id: str, *, db=None, now=None) -> list[PolicyChange]:
    """Apply compact, explainable tightening rules from plan §8.3."""
    if get_settings().stub_mode:
        require_demo_user(user_id)
        return []
    db = db if db is not None else get_db()
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=7)
    changes = []
    policy = await get_policy(user_id)
    forged = await db.events.count_documents(
        {"user_id": user_id, "type": {"$in": ["forged", "promoted"]}, "ts": {"$gte": since}}
    )
    pruned = await db.events.count_documents(
        {"user_id": user_id, "type": "pruned", "ts": {"$gte": since}}
    )
    if forged and pruned / forged > 0.5:
        current = int(policy.thresholds.get("min_support", 3))
        changes.append(
            await record_change(
                user_id,
                "thresholds.min_support",
                current + 1,
                "tighten",
                f"{pruned} of the last {forged} forged tools were pruned",
                [],
            )
        )
        policy = await get_policy(user_id)

    false_actions = await db.runs.count_documents(
        {"user_id": user_id, "outcome": "false_action", "started_at": {"$gte": since}}
    )
    if false_actions:
        promote = dict(policy.thresholds.get("promote", {}))
        current = int(promote.get("success_streak", 2))
        promote["success_streak"] = current + 4
        changes.append(
            await record_change(
                user_id,
                "thresholds.promote",
                promote,
                "tighten",
                f"{false_actions} false action(s) in the last 7 days",
                [],
            )
        )
        policy = await get_policy(user_id)

    shown = await db.suggestion_impressions.count_documents(
        {"user_id": user_id, "shown_at": {"$gte": since}}
    )
    accepted = await db.patterns.count_documents(
        {
            "user_id": user_id,
            "status": {"$in": ["accepted", "toolified"]},
            "accepted_at": {"$gte": since},
        }
    )
    cap = int(policy.thresholds.get("max_suggestions_per_day", 3))
    if shown >= 3 and accepted / shown < 0.3 and cap > 1:
        changes.append(
            await record_change(
                user_id,
                "thresholds.max_suggestions_per_day",
                cap - 1,
                "tighten",
                f"Only {accepted} of {shown} suggestions were accepted",
                [],
            )
        )
    return changes
