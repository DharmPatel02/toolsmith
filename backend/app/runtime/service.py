from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.contracts import Run, RunResult, SandboxResult
from app.db import get_db
from app.events import publish
from app.fixtures import fixture, require_demo_user
from app.policy.service import get_policy
from app.runtime.lineage import resolve_deps
from app.sandbox.runner import run_in_sandbox
from app.search import search_tools


def _run_result(
    *,
    run_id: str,
    route: str,
    tool_id: str | None,
    score: float | None,
    sandbox: SandboxResult | None = None,
) -> RunResult:
    return RunResult(
        run_id=run_id,
        mode="dry_run",
        output=(sandbox.output if sandbox else {}),
        intended_writes=(sandbox.intended_writes if sandbox else []),
        needs_confirm=True,
        duration_ms=(sandbox.duration_ms if sandbox else 0),
        tokens=0,
        route=route,
        tool_id=tool_id,
        score=score,
    )


def _tool_identity(tool: dict) -> str:
    return str(tool.get("tool_id") or tool.get("_id"))


async def _active_tool_and_version(user_id: str, tool_id: str) -> tuple[dict, dict]:
    db = get_db()
    tool = await db.tools.find_one(
        {
            "$or": [{"_id": tool_id}, {"tool_id": tool_id}],
            "user_id": user_id,
            "status": {"$ne": "deprecated"},
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


async def _run_live_tool(user_id: str, tool_id: str, params: dict, *, score: float) -> RunResult:
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
    mode = "dry_run" if tool.get("trust", "dry_run") == "dry_run" else "live"
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
    }
    await db.runs.insert_one(run_doc)
    try:
        from app.trust.service import update_after_run

        await update_after_run(Run(**run_doc))
    except (ImportError, NotImplementedError):
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
    return await _run_live_tool(user_id, tool_id, params, score=1.0)
