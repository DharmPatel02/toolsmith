"""Intended actions on runs (approval-first automation, plan §1.3 / §1.4).

A tool's `ctx.action(...)` calls come back from the sandbox as intended writes. On a confirmed run:
  - "auto" steps (e.g. tracker.upsert) are executed now through the user's connectors;
  - "approval" steps (e.g. slack.post, jira.create) wait on the run (`awaiting_approval`) until an
    approver approves (executed) or rejects them (feedback for the tool's next version).
Every executed action keeps its receipt so `revert_run` can undo exactly what happened.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.automation import connectors, executors
from app.db import get_db


def items_from_writes(writes: list[Any]) -> list[dict]:
    """Sandbox intended writes -> action items (files are not actions)."""
    items = []
    for w in writes:
        kind = w.kind if hasattr(w, "kind") else w["kind"]
        if not kind.startswith("action:"):
            continue
        action = kind.removeprefix("action:")
        payload = (w.payload if hasattr(w, "payload") else w.get("payload")) or {}
        items.append(
            {
                "kind": action,
                "payload": payload,
                "description": executors.describe(action, payload),
                "needs_approval": executors.needs_approval(action),
                "status": "pending",
                "receipt": None,
                "error": None,
            }
        )
    return items


async def execute_items(user_id: str, items: list[dict], *, approved: bool) -> list[dict]:
    """Runs pending items: auto ones always, approval ones only when `approved`."""
    for item in items:
        if item["status"] != "pending" or (item["needs_approval"] and not approved):
            continue
        try:
            item["receipt"] = await executors.execute(user_id, item["kind"], item["payload"])
            item["status"] = "done"
            item["executed_at"] = datetime.now(timezone.utc)
        except connectors.MissingPermission as exc:
            item["status"], item["error"] = "failed", f"not connected: {exc}"
        except (ConnectionError, LookupError, OSError) as exc:
            item["status"], item["error"] = "failed", str(exc)[:300]
    return items


def run_status(items: list[dict], ok: bool) -> str:
    if not ok or any(i["status"] == "failed" for i in items):
        return "failed"
    if any(i["status"] == "pending" and i["needs_approval"] for i in items):
        return "awaiting_approval"
    return "done"


async def _run_for(user_id: str, run_id: str) -> dict:
    run = await get_db().runs.find_one({"_id": run_id, "user_id": user_id})
    if not run:
        raise LookupError("Unknown run")
    return run


async def list_approvals(user_id: str) -> list[dict]:
    db = get_db()
    runs = (
        await db.runs.find({"user_id": user_id, "status": "awaiting_approval"})
        .sort("started_at", -1)
        .to_list(length=100)
    )
    out = []
    for run in runs:
        tool = await db.tools.find_one({"_id": run["tool_id"]}, {"title": 1, "name": 1}) or {}
        pending = [i for i in run.get("actions", []) if i["status"] == "pending"]
        summary = (run.get("output") or {}).get("summary")
        out.append(
            {
                "run_id": run["_id"],
                "tool_id": run["tool_id"],
                "tool_title": tool.get("title") or tool.get("name"),
                "created_at": run["started_at"],
                "summary": summary,
                "actions": [public_item(i) for i in pending],
            }
        )
    return out


async def decide(user_id: str, run_id: str, decision: str, note: str | None) -> dict:
    db = get_db()
    run = await _run_for(user_id, run_id)
    if run.get("status") != "awaiting_approval":
        raise ValueError(f"run is {run.get('status')}, not awaiting approval")
    items = run.get("actions", [])
    if decision == "approve":
        await execute_items(user_id, items, approved=True)
        status = run_status(items, True)
    else:
        for item in items:
            if item["status"] == "pending":
                item["status"] = "rejected"
        status = "rejected"
        pattern = await db.patterns.find_one({"tool_id": run["tool_id"]}, {"_id": 1}) or {}
        await db.feedback.insert_one(
            {
                "user_id": user_id,
                "tool_id": run["tool_id"],
                "run_id": run_id,
                "pattern_id": pattern.get("_id"),
                "kind": "reject",
                "decision": "reject",
                "reason": note or "",
                "created_at": datetime.now(timezone.utc),
            }
        )
    await db.runs.update_one(
        {"_id": run_id},
        {"$set": {"actions": items, "status": status, "decided_at": datetime.now(timezone.utc)}},
    )
    return {
        "ok": True,
        "status": status,
        "executed": sum(i["status"] == "done" and i["needs_approval"] for i in items),
        "failed": [i["error"] for i in items if i["status"] == "failed"],
    }


async def revert_run(user_id: str, run_id: str) -> dict:
    """Undo every executed action of a run, newest first."""
    db = get_db()
    run = await _run_for(user_id, run_id)
    if run.get("status") == "reverted":
        return {"ok": True, "undone": 0, "already": True}
    items = run.get("actions", [])
    undone, errors = 0, []
    for item in reversed(items):
        if item["status"] != "done" or not item.get("receipt"):
            if item["status"] == "pending":
                item["status"] = "cancelled"
            continue
        try:
            await executors.compensate(user_id, item["receipt"])
            item["status"] = "undone"
            undone += 1
        except (connectors.MissingPermission, ConnectionError, LookupError, OSError) as exc:
            errors.append(f"{item['kind']}: {exc}")
    status = "reverted" if not errors else run.get("status")
    await db.runs.update_one({"_id": run_id}, {"$set": {"actions": items, "status": status}})
    return {"ok": not errors, "undone": undone, "errors": errors}


async def tool_runs(user_id: str, tool_id: str, limit: int = 20) -> list[dict]:
    runs = (
        await get_db()
        .runs.find({"user_id": user_id, "tool_id": tool_id})
        .sort("started_at", -1)
        .to_list(length=limit)
    )
    return [
        {
            "run_id": r["_id"],
            "started_at": r["started_at"],
            "mode": r.get("mode", "dry_run"),
            "outcome": r.get("outcome"),
            "status": r.get("status", "done"),
            "duration_ms": r.get("duration_ms", 0),
            "actions": [public_item(i) for i in r.get("actions", [])],
        }
        for r in runs
    ]


def public_item(item: dict) -> dict:
    return {
        k: item.get(k)
        for k in ("kind", "payload", "description", "needs_approval", "status", "receipt", "error")
    }
