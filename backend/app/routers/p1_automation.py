"""Approval-first automation routes (plan §1.3/§1.4): approvals inbox, run undo, run history,
tool delete, and ending a capture session now (live demo). Live data only; fixture mode returns
empty/neutral answers so the UI still renders."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.contracts import Contract
from app.fixtures import require_demo_user
from app.runtime import actions, lifecycle

router = APIRouter(tags=["p1-automation"])


def _user() -> str:
    user_id = get_settings().demo_user_id
    require_demo_user(user_id)
    return user_id


def _live() -> bool:
    return not get_settings().stub_mode


class Decision(Contract):
    decision: Literal["approve", "reject"]
    note: str | None = None


class DeleteRequest(Contract):
    never_suggest_again: bool = False


@router.get("/approvals")
async def approvals():
    return await actions.list_approvals(_user()) if _live() else []


@router.post("/approvals/{run_id}")
async def decide(run_id: str, body: Decision):
    if body.decision == "reject" and not (body.note or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    if not _live():
        return {
            "ok": True,
            "status": "rejected" if body.decision == "reject" else "done",
            "executed": 0,
        }
    try:
        return await actions.decide(_user(), run_id, body.decision, body.note)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/runs/{run_id}/revert")
async def revert(run_id: str):
    if not _live():
        return {"ok": True, "undone": 0}
    return await actions.revert_run(_user(), run_id)


@router.get("/tools/{tool_id}/runs")
async def runs(tool_id: str):
    return await actions.tool_runs(_user(), tool_id) if _live() else []


@router.post("/tools/{tool_id}/delete")
async def delete(tool_id: str, body: DeleteRequest | None = None):
    if not _live():
        return {"ok": True, "tool_id": tool_id}
    body = body or DeleteRequest()
    return await lifecycle.delete_tool(
        _user(), tool_id, never_suggest_again=body.never_suggest_again
    )


@router.post("/capture/sessions/close")
async def close_sessions():
    """Close the user's open sessions now (no 30-min idle wait) so they're mined right away."""
    if not _live():
        return {"ok": True, "sessions_closed": 0}
    from app.ingest.service import close_idle
    from app.ingest.sessionizer import IDLE

    closed = await close_idle(_user(), now=datetime.now(timezone.utc) + IDLE + timedelta(seconds=1))
    return {"ok": True, "sessions_closed": len(closed or [])}
