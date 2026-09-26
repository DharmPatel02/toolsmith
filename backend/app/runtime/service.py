from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.contracts import Run, RunResult, SandboxResult
from app.db import get_db
from app.events import publish
from app.fixtures import fixture, require_demo_user
from app.policy.service import get_policy
from app.runtime import actions as run_actions
from app.runtime.lineage import resolve_deps
from app.sandbox.runner import run_in_sandbox
from app.search import search_tools


def _writes(sandbox: SandboxResult | None) -> list[dict]:
    """Runner dataclasses -> contract dicts (path, kind, bytes, payload)."""
    out = []
    for w in sandbox.intended_writes if sandbox else []:
        get = (
            (lambda k, w=w: w.get(k))
            if isinstance(w, dict)
            else (lambda k, w=w: getattr(w, k, None))
        )
        out.append(
            {
                "path": get("path"),
                "kind": get("kind") or "file",
                "bytes": get("bytes"),
                "payload": get("payload"),
            }
        )
    return out


def _run_result(
    *,
    run_id: str,
    route: str,
    tool_id: str | None,
    score: float | None,
    sandbox: SandboxResult | None = None,
    mode: str = "dry_run",
    status: str | None = None,
    items: list[dict] | None = None,
) -> RunResult:
    writes = _writes(sandbox)
    preview = mode == "dry_run"
    return RunResult(
        run_id=run_id,
        mode=mode,
        output=(sandbox.output if sandbox else {}),
        intended_writes=writes,
        # a preview needs a yes before anything is written or sent; a confirmed run doesn't
        needs_confirm=preview and bool(writes) and bool(sandbox and sandbox.ok),
        duration_ms=(sandbox.duration_ms if sandbox else 0),
        tokens=0,
        route=route,
        tool_id=tool_id,
        score=score,
        status=status,
        actions=[run_actions.public_item(i) for i in (items or [])],
    )


def _tool_identity(tool: dict) -> str:
    return str(tool.get("tool_id") or tool.get("_id"))


async def update_after_run(run: Run | dict) -> None:
    from app.trust.service import update_after_run as trust_update_after_run

    # P2's ladder reads a plain dict (run.get(...)); a pydantic Run would raise AttributeError
    await trust_update_after_run(run if isinstance(run, dict) else run.model_dump(by_alias=True))


async def _active_tool_and_version(user_id: str, tool_id: str) -> tuple[dict, dict]:
    db = get_db()
    tool = await db.tools.find_one(
        {
            "$or": [{"_id": tool_id}, {"tool_id": tool_id}],
            "user_id": user_id,
            "status": {"$nin": ["deprecated", "deleted"]},
        }
    )
    if not tool:
        raise LookupError("Unknown tool")
    version_number = tool.get("active_version", 1)
    version = None
    if tool.get("version") and tool["version"].get("version") == version_number:
        version = tool["version"]
    if version is None:
        version = await db.tool_versions.find_one(
            {"tool_id": _tool_identity(tool), "version": version_number}
        )
    if not version:
        raise LookupError("Active tool version is missing")
    return tool, version


async def _run_live_tool(
    user_id: str, tool_id: str, params: dict, *, score: float, confirm: bool = False
) -> RunResult:
    db = get_db()
    tool, version = await _active_tool_and_version(user_id, tool_id)
    resolved = await resolve_deps(user_id, _tool_identity(tool))
    deps = {dep.name: dep.code for dep in resolved}
    run_id = f"run:{uuid4().hex}"
    now = datetime.now(timezone.utc)
    memory_id = f"wm:{run_id}"
    await db.working_memory.insert_one(
        {
            "_id": memory_id,
            "user_id": user_id,
            "tool_id": _tool_identity(tool),
            "run_id": run_id,
            "static": {
                "tool": tool.get("name", _tool_identity(tool)),
                "version": version["version"],
                "requires": version.get("requires", {}),
            },
            "dynamic": params,
            "expires_at": now + timedelta(hours=1),
            "created_at": now,
        }
    )
    # a preview never writes or sends anything; a confirmed run does (auto steps now, approval
    # steps after an approver says yes)
    mode = "live" if confirm else "dry_run"
    try:
        sandbox = await run_in_sandbox(
            version["code"],
            "run",
            params,
            inputs={},
            mode=mode,
            scopes=(version.get("requires") or {}).get("scopes", []),
            deps=deps,
        )
    except NotImplementedError as exc:
        sandbox = SandboxResult(
            ok=False,
            output={"error": str(exc)},
            intended_writes=[],
            stdout="",
            error=str(exc),
            duration_ms=0,
        )
    items = run_actions.items_from_writes(sandbox.intended_writes)
    if confirm and sandbox.ok:
        await run_actions.execute_items(user_id, items, approved=False)
    status = run_actions.run_status(items, sandbox.ok) if confirm else "preview"
    run_doc = {
        "_id": run_id,
        "tool_id": _tool_identity(tool),
        "version": version["version"],
        "user_id": user_id,
        "tier": tool.get("tier", "lean"),
        "trust_at_run": tool.get("trust", "dry_run"),
        "outcome": "success" if sandbox.ok else "failed",
        "inputs": params,
        "output_ref": None,
        "user_edited": False,
        "cost": {"tokens": 0, "usd": 0},
        "duration_ms": sandbox.duration_ms,
        "error": sandbox.error,
        "started_at": now,
        "mode": mode,
        "status": status,
        "actions": items,
        "output": {"summary": (sandbox.output or {}).get("summary")},
    }
    await db.runs.insert_one(run_doc)
    if confirm:  # previews don't move the trust ladder; confirmed runs do
        try:
            await update_after_run({**run_doc, "user_confirmed": True})
        except (ImportError, NotImplementedError, ValueError):
            pass
    await publish(
        user_id,
        "run_completed",
        {
            "run_id": run_id,
            "tool_id": _tool_identity(tool),
            "ok": sandbox.ok,
            "working_memory_id": memory_id,
        },
    )
    return _run_result(
        run_id=run_id,
        route="found",
        tool_id=_tool_identity(tool),
        score=score,
        sandbox=sandbox,
        mode=mode,
        status=status,
        items=items,
    )


async def run_by_intent(user_id: str, intent: str, inputs: dict) -> RunResult:
    from app.config import get_settings

    if get_settings().stub_mode:
        require_demo_user(user_id)
        return RunResult(**fixture("run_result.json"))
    policy = await get_policy(user_id)
    thresholds = policy.thresholds
    hits = await search_tools(user_id, intent, k=1)
    if not hits:
        run_id = f"run:{uuid4().hex}"
        await get_db().sessions.insert_one(
            {
                "_id": f"not_found:{uuid4().hex}",
                "user_id": user_id,
                "started_at": datetime.now(timezone.utc),
                "ended_at": datetime.now(timezone.utc),
                "status": "closed",
                "source": "runtime",
                "signature_seq": [],
                "intent_summary": intent,
                "intent_embedding": [],
                "tokens": 0,
                "minutes": 0,
                "artifacts": {"inputs": [str(inputs)]},
                "outcome": "not_found",
            }
        )
        return _run_result(run_id=run_id, route="not_found", tool_id=None, score=None)
    best = hits[0]
    if best.score >= float(thresholds.get("T_high", 0.82)):
        return await _run_live_tool(user_id, best.tool_id, inputs, score=best.score)
    if best.score >= float(thresholds.get("T_low", 0.62)):
        return _run_result(
            run_id=f"run:{uuid4().hex}",
            route="related",
            tool_id=best.tool_id,
            score=best.score,
        )
    return _run_result(
        run_id=f"run:{uuid4().hex}",
        route="not_found",
        tool_id=best.tool_id,
        score=best.score,
    )


async def run_tool(user_id: str, tool_id: str, params: dict, confirm: bool = False) -> RunResult:
    from app.config import get_settings

    if get_settings().stub_mode:
        require_demo_user(user_id)
        if tool_id != "tool_uc1":
            raise LookupError("Unknown fixture tool")
        # Even confirm=True never executes code in Phase 0.
        return RunResult(**fixture("run_result.json"))
    return await _run_live_tool(user_id, tool_id, params, score=1.0, confirm=confirm)
