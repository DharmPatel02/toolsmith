"""Automation plan, connectors (OAuth-style grant against the real mock site) and executors."""

import importlib.util
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from app.automation import connectors, executors
from app.automation.plan import automation_plan, missing_permissions
from app.forge import deps
from app.routers import p3_connectors
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient

MOCKSITE = Path(__file__).resolve().parents[3] / "mocksite"
_spec = importlib.util.spec_from_file_location("mocksite_server_auto", MOCKSITE / "server.py")
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

UC2 = [
    "email.open",
    "pdf.extract:invoice",
    "table.join:po",
    "invoice.validate",
    "tracker.upsert",
    "slack.post",
    "jira.create",
]


@pytest.fixture
def env(monkeypatch):
    server.apps.reset()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    site = f"http://127.0.0.1:{httpd.server_address[1]}"
    monkeypatch.setenv("MOCKSITE_URL", site)
    monkeypatch.setenv("MOCKSITE_PUBLIC_URL", site)
    monkeypatch.setenv("API_BASE", "http://localhost:8000")
    monkeypatch.setenv("WEB_BASE", "http://localhost:3000")
    db = AsyncMongoMockClient()["p3_auto"]
    deps.use_db(db)
    yield site, db
    deps.use_db(None)
    httpd.shutdown()


def browser_allow(consent_url: str, decision: str = "allow") -> dict:
    """Clicks Allow/Deny on the mock consent page; returns the callback query the API receives."""
    q = parse_qs(urlparse(consent_url).query)
    site = consent_url.split("/oauth/")[0]
    assert httpx.get(consent_url).status_code == 200
    r = httpx.post(
        f"{site}/oauth/decide",
        data={
            "app": q["app"][0],
            "scopes": q["scopes"][0],
            "state": q["state"][0],
            "redirect_uri": q["redirect_uri"][0],
            "decision": decision,
        },
    )
    assert r.status_code == 303
    callback = urlparse(r.headers["location"])
    assert callback.path == "/connectors/callback"
    return {k: v[0] for k, v in parse_qs(callback.query).items()}


async def grant(app: str) -> None:
    start = await connectors.start_connect("u_1", app)
    back = browser_allow(start["consent_url"])
    assert (await connectors.complete(back["state"], back.get("code")))["status"] == "connected"


def test_plan_classifies_steps_and_permissions():
    plan = automation_plan({"signature": UC2, "est_minutes_saved_week": 45})
    kinds = {s["step"]: s["automation"] for s in plan["steps"]}
    assert kinds["pdf.extract:invoice"] == "auto" and kinds["slack.post"] == "approval"
    assert plan["counts"] == {"auto": 5, "approval": 2, "manual": 0}
    assert {p["connector"] for p in missing_permissions(plan)} == {
        "email",
        "tracker",
        "slack",
        "jira",
    }
    granted = automation_plan({"signature": UC2}, {"slack": ["chat:write"], "email": ["mail:read"]})
    assert {p["connector"] for p in missing_permissions(granted)} == {"tracker", "jira"}
    unknown = automation_plan({"signature": ["robot.dance"]})
    assert unknown["steps"][0]["automation"] == "manual"


async def test_connect_allow_deny_revoke_require(env):
    with pytest.raises(connectors.MissingPermission):
        await connectors.require("u_1", "slack", ["chat:write"])
    await grant("slack")
    assert (await connectors.require("u_1", "slack", ["chat:write"])).startswith("tok_")
    listing = {c["app"]: c for c in await connectors.list_connectors("u_1")}
    assert listing["slack"]["status"] == "connected" and "token" not in str(listing)
    assert await connectors.granted("u_1") == {"slack": ["chat:write"]}

    start = await connectors.start_connect("u_1", "jira")
    back = browser_allow(start["consent_url"], "deny")
    assert (await connectors.complete(back["state"], back.get("code"), back.get("error")))[
        "status"
    ] == "denied"
    with pytest.raises(LookupError):  # state is one-time
        await connectors.complete(back["state"], "x")

    await connectors.revoke("u_1", "slack")
    with pytest.raises(connectors.MissingPermission):
        await connectors.require("u_1", "slack", ["chat:write"])


async def test_execute_and_compensate_on_mock_apps(env):
    site, _ = env
    for app in ("slack", "jira", "tracker"):
        await grant(app)
    slack = await executors.execute(
        "u_1", "slack.post", {"channel": "#warehouse", "text": "INV-2202 qty over PO"}
    )
    jira = await executors.execute("u_1", "jira.create", {"summary": "INV-2202 qty over PO"})
    row = await executors.execute(
        "u_1", "tracker.upsert", {"ref": "INV-2202", "status": "received"}
    )
    upd = await executors.execute(
        "u_1", "tracker.upsert", {"ref": "INV-2202", "status": "mismatch"}
    )
    assert "INV-2202 qty over PO" in httpx.get(f"{site}/apps/slack").text
    assert jira["id"].startswith("WH-") and row["created"] and not upd["created"]

    await executors.compensate("u_1", upd)  # restores status "received"
    rows = httpx.get(f"{site}/api/tracker/rows").json()
    assert rows[0]["status"] == "received"
    for receipt in (slack, jira, row):
        await executors.compensate("u_1", receipt)
    assert "INV-2202 qty over PO" not in httpx.get(f"{site}/apps/slack").text
    assert httpx.get(f"{site}/api/jira/issues").json() == []
    assert httpx.get(f"{site}/api/tracker/rows").json() == []
    assert executors.needs_approval("slack.post") and not executors.needs_approval("tracker.upsert")


async def test_routes(env):
    app = FastAPI()
    app.include_router(p3_connectors.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert len((await c.get("/connectors")).json()) == 4
        start = (await c.post("/connectors/slack/connect", json={})).json()
        back = browser_allow(start["consent_url"])
        r = await c.get("/connectors/callback", params=back)
        assert r.status_code == 303 and r.headers["location"].endswith("app=slack&status=connected")
        plan = (await c.post("/automation/plan", json={"signature": UC2})).json()
        slack = next(p for p in plan["permissions"] if p["connector"] == "slack")
        assert slack["granted"] is True
        assert (await c.post("/connectors/github/connect", json={})).status_code == 404
        assert (await c.post("/connectors/slack/revoke")).json()["status"] == "revoked"
