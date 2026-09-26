"""Approval-first runtime: preview -> confirm (auto actions now) -> approvals -> undo; delete tool.

Real sandbox (process mode) + the real mock apps; DB is mongomock behind every get_db seam.
"""

import importlib.util
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from app.automation import connectors
from app.forge import deps
from app.gate.service import check_side_effects
from app.runtime import actions, lifecycle
from app.runtime import service as runtime
from mongomock_motor import AsyncMongoMockClient

MOCKSITE = Path(__file__).resolve().parents[3] / "mocksite"
_spec = importlib.util.spec_from_file_location("mocksite_server_rt", MOCKSITE / "server.py")
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

TOOL_CODE = """
def run(ctx, ref, mismatch=False, **params):
    ctx.action("tracker.upsert", ref=ref, status="mismatch" if mismatch else "matched")
    if mismatch:
        ctx.action("slack.post", channel="#warehouse", text=ref + ": quantity over PO")
        ctx.action("jira.create", summary=ref + " quantity mismatch")
    return {"summary": ref + (" needs review" if mismatch else " matched")}
"""


@pytest.fixture
def env(monkeypatch):
    server.apps.reset()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    site = f"http://127.0.0.1:{httpd.server_address[1]}"
    for var, value in (
        ("MOCKSITE_URL", site),
        ("MOCKSITE_PUBLIC_URL", site),
        ("API_BASE", "http://localhost:8000"),
    ):
        monkeypatch.setenv(var, value)
    db = AsyncMongoMockClient()["rt"]
    deps.use_db(db)
    for module in (runtime, actions, lifecycle):
        monkeypatch.setattr(module, "get_db", lambda: db)
    monkeypatch.setattr(runtime, "resolve_deps", AsyncMock(return_value=[]))
    monkeypatch.setattr(runtime, "update_after_run", AsyncMock())
    monkeypatch.setattr(runtime, "publish", AsyncMock())
    monkeypatch.setattr(lifecycle, "dependents", AsyncMock(return_value=[]))
    yield site, db
    deps.use_db(None)
    httpd.shutdown()


async def seed_tool(db):
    await db.tools.insert_one(
        {
            "_id": "tool_inv",
            "user_id": "u_1",
            "name": "invoice_check",
            "title": "Invoice check",
            "status": "active",
            "trust": "dry_run",
            "active_version": 1,
            "version": {
                "version": 1,
                "code": TOOL_CODE,
                "requires": {"scopes": ["app:tracker", "app:slack", "app:jira"]},
            },
        }
    )
    await db.patterns.insert_one(
        {
            "_id": "pat_uc2",
            "user_id": "u_1",
            "status": "toolified",
            "tool_id": "tool_inv",
            "signature": ["email.open", "slack.post"],
        }
    )


async def grant(app):
    start = await connectors.start_connect("u_1", app)
    q = parse_qs(urlparse(start["consent_url"]).query)
    site = start["consent_url"].split("/oauth/")[0]
    r = httpx.post(
        f"{site}/oauth/decide",
        data={
            "app": app,
            "scopes": q["scopes"][0],
            "state": q["state"][0],
            "redirect_uri": q["redirect_uri"][0],
            "decision": "allow",
        },
    )
    back = {k: v[0] for k, v in parse_qs(urlparse(r.headers["location"]).query).items()}
    await connectors.complete(back["state"], back["code"])


def mock_app(site, path):
    return httpx.get(f"{site}{path}").json()


async def test_preview_then_confirm_then_approve_then_undo(env):
    site, db = env
    await seed_tool(db)
    params = {"ref": "INV-2202", "mismatch": True}

    preview = (
        await runtime.run_tool("u_1", "tool_inv", params, confirm=False)
        if False
        else await runtime._run_live_tool("u_1", "tool_inv", params, score=1.0)
    )
    assert preview.status == "preview" and preview.mode == "dry_run" and preview.needs_confirm
    assert [a["kind"] for a in preview.actions] == ["tracker.upsert", "slack.post", "jira.create"]
    assert preview.intended_writes[1].payload["channel"] == "#warehouse"
    assert mock_app(site, "/api/tracker/rows") == []  # a preview sends nothing

    # confirmed but nothing connected: fails cleanly, still nothing sent
    failed = await runtime._run_live_tool("u_1", "tool_inv", params, score=1.0, confirm=True)
    assert failed.status == "failed" and "not connected" in failed.actions[0]["error"]
    assert mock_app(site, "/api/tracker/rows") == []

    for app in ("tracker", "slack", "jira"):
        await grant(app)
    run = await runtime._run_live_tool("u_1", "tool_inv", params, score=1.0, confirm=True)
    assert run.status == "awaiting_approval" and run.mode == "live" and not run.needs_confirm
    assert mock_app(site, "/api/tracker/rows")[0]["status"] == "mismatch"  # auto step done now
    assert mock_app(site, "/api/slack/messages") == []  # approval steps wait

    inbox = await actions.list_approvals("u_1")
    assert [i["run_id"] for i in inbox] == [run.run_id]
    assert {a["kind"] for a in inbox[0]["actions"]} == {"slack.post", "jira.create"}

    decided = await actions.decide("u_1", run.run_id, "approve", None)
    assert decided["status"] == "done" and decided["executed"] == 2
    assert "INV-2202: quantity over PO" in mock_app(site, "/api/slack/messages")[0]["text"]
    assert len(mock_app(site, "/api/jira/issues")) == 1
    assert await actions.list_approvals("u_1") == []
    with pytest.raises(ValueError):
        await actions.decide("u_1", run.run_id, "approve", None)

    history = await actions.tool_runs("u_1", "tool_inv")
    assert [h["status"] for h in history][:1] == ["done"]

    undone = await actions.revert_run("u_1", run.run_id)
    assert undone == {"ok": True, "undone": 3, "errors": []}
    assert mock_app(site, "/api/tracker/rows") == []
    assert mock_app(site, "/api/slack/messages") == [] and mock_app(site, "/api/jira/issues") == []
    assert (await db.runs.find_one({"_id": run.run_id}))["status"] == "reverted"


async def test_reject_records_feedback_and_clean_invoice_needs_no_approval(env):
    site, db = env
    await seed_tool(db)
    for app in ("tracker", "slack", "jira"):
        await grant(app)
    clean = await runtime._run_live_tool(
        "u_1", "tool_inv", {"ref": "INV-2201"}, score=1.0, confirm=True
    )
    assert clean.status == "done"  # only the auto tracker step

    run = await runtime._run_live_tool(
        "u_1", "tool_inv", {"ref": "INV-2205", "mismatch": True}, score=1.0, confirm=True
    )
    res = await actions.decide("u_1", run.run_id, "reject", "price change was agreed by phone")
    assert res["status"] == "rejected" and mock_app(site, "/api/slack/messages") == []
    fb = await db.feedback.find_one({"run_id": run.run_id})
    assert fb["pattern_id"] == "pat_uc2" and fb["reason"] == "price change was agreed by phone"


async def test_delete_blocked_then_resuggest_or_never(env):
    site, db = env
    await seed_tool(db)
    await db.runs.insert_one(
        {
            "_id": "r1",
            "user_id": "u_1",
            "tool_id": "tool_inv",
            "status": "awaiting_approval",
            "started_at": datetime.now(timezone.utc),
        }
    )
    blocked = await lifecycle.delete_tool("u_1", "tool_inv")
    assert not blocked["ok"] and "waiting for approval" in blocked["blocked_reason"]
    await db.runs.update_one({"_id": "r1"}, {"$set": {"status": "done"}})

    lifecycle.dependents.return_value = ["tool_report"]
    assert "depend" in (await lifecycle.delete_tool("u_1", "tool_inv"))["blocked_reason"]
    lifecycle.dependents.return_value = []

    await db.policy.insert_one(
        {"_id": "policy:u_1", "thresholds": {"resuggest_after_delete_minutes": 2}, "rules": []}
    )
    assert (await lifecycle.delete_tool("u_1", "tool_inv"))["ok"]
    tool = await db.tools.find_one({"_id": "tool_inv"})
    pattern = await db.patterns.find_one({"_id": "pat_uc2"})
    assert tool["status"] == "deleted" and pattern["status"] == "mined"
    assert pattern["deleted_tool_id"] == "tool_inv" and "tool_id" not in pattern
    cooldown = pattern["cooldown_until"].replace(tzinfo=timezone.utc) - pattern[
        "deleted_at"
    ].replace(tzinfo=timezone.utc)
    assert cooldown.total_seconds() == 120
    with pytest.raises(LookupError):
        await lifecycle.delete_tool("u_1", "tool_inv")
    with pytest.raises(LookupError):  # the runtime no longer finds a deleted tool
        await runtime._run_live_tool("u_1", "tool_inv", {"ref": "x"}, score=1.0)

    # never again: rule on this pattern only
    await db.tools.insert_one({"_id": "tool_b", "user_id": "u_1", "name": "b", "status": "active"})
    await db.patterns.insert_one(
        {"_id": "pat_b", "user_id": "u_1", "tool_id": "tool_b", "signature": ["x"]}
    )
    assert (await lifecycle.delete_tool("u_1", "tool_b", never_suggest_again=True))["ok"]
    assert (await db.patterns.find_one({"_id": "pat_b"}))["status"] == "declined"
    rules = (await db.policy.find_one({"_id": "policy:u_1"}))["rules"]
    assert rules[-1]["pattern_id"] == "pat_b" and "blocked_signatures" not in rules[-1]


def test_gate_treats_actions_as_scoped_side_effects():
    ok = check_side_effects(
        {
            "requires": {"scopes": ["app:slack", "write:outputs"]},
            "spec": {"outputs": {"files": ["report.html"]}},
        },
        ["report.html", "action:slack.post"],
    )
    assert ok["ok"] and ok["actions"] == ["action:slack.post"]
    bad = check_side_effects({"requires": {"scopes": []}}, ["action:jira.create"])
    assert not bad["ok"] and "app:jira" in bad["reason"]


def test_routes_in_fixture_mode():
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    assert client.get("/approvals").json() == []
    assert client.post("/approvals/r1", json={"decision": "reject"}).status_code == 422
    assert client.post("/approvals/r1", json={"decision": "approve"}).json()["ok"]
    assert client.post("/runs/r1/revert").json() == {"ok": True, "undone": 0}
    assert client.get("/tools/tool_uc1/runs").json() == []
    assert client.post("/tools/tool_uc1/delete", json={"never_suggest_again": True}).json()["ok"]
    assert client.post("/capture/sessions/close").json()["ok"]
