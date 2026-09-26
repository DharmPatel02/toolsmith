"""Intended actions -> real calls on connected apps, and how to undo them (plan §1.3, §1.4).

Tools never touch the network: they return `action:<kind>` intended writes. After the user (or the
approver) confirms, the runtime calls `execute()` for each one; the receipt it returns is stored on
the run so `compensate()` can undo exactly that effect later.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.automation import connectors
from app.automation.plan import STEPS

# kind -> (app, scope, method, path, id field in the app's response)
ACTIONS = {
    "slack.post": ("slack", "chat:write", "POST", "/api/slack/messages", "id"),
    "jira.create": ("jira", "issues:write", "POST", "/api/jira/issues", "key"),
    "tracker.upsert": ("tracker", "rows:write", "POST", "/api/tracker/rows", "id"),
}


def needs_approval(kind: str) -> bool:
    step = STEPS.get(kind)
    return step is None or step.automation != "auto"


def describe(kind: str, payload: dict) -> str:
    """One line for previews and the approvals inbox."""
    if kind == "slack.post":
        return f"Post in {payload.get('channel', '#general')}: {payload.get('text', '')}"
    if kind == "jira.create":
        return f"Open Jira ticket: {payload.get('summary', '')}"
    if kind == "tracker.upsert":
        ref, status, note = (payload.get(k, "") for k in ("ref", "status", "note"))
        return f"Tracker {ref}: {status} {note}".strip()
    return f"{kind}: {payload}"


async def execute(user_id: str, kind: str, payload: dict) -> dict:
    """Runs one action and returns its receipt.

    Raises MissingPermission, ConnectionError or LookupError."""
    if kind not in ACTIONS:
        raise LookupError(f"no executor for action {kind}")
    app, scope, method, path, id_field = ACTIONS[kind]
    token = await connectors.require(user_id, app, [scope])
    result = await connectors.http(method, connectors.apps_url() + path, payload, token)
    return {
        "kind": kind,
        "app": app,
        "id": result.get(id_field),
        "created": result.get("created", True),
        "previous": result.get("previous"),
        "executed_at": datetime.now(UTC).isoformat(),
    }


async def compensate(user_id: str, receipt: dict) -> dict:
    """Undo one executed action from its receipt."""
    kind = receipt["kind"]
    app, scope, _, path, _ = ACTIONS[kind]
    token = await connectors.require(user_id, app, [scope])
    base = connectors.apps_url() + path
    if kind == "tracker.upsert" and not receipt.get("created", True):
        # the row existed before this run: put the old values back instead of deleting it
        await connectors.http(
            "PATCH", f"{base}/{receipt['id']}", receipt.get("previous") or {}, token
        )
        return {"kind": kind, "undone": "restored"}
    await connectors.http("DELETE", f"{base}/{receipt['id']}", None, token)
    return {"kind": kind, "undone": "deleted"}
