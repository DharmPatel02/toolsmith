"""Connected apps and permission grants (plan §1.2): the "ask for credentials" step.

OAuth-style: `start_connect` stores a one-time `state` and returns the app's consent URL; the app
redirects back to `/connectors/callback?code&state`; `complete` swaps the code for a token.
Grants live in `connectors`; tokens live apart in `connector_tokens` and never leave the API.
For the demo the "apps" are the mock Slack / Jira / tracker / inbox on the mock site.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from app.forge import deps

APPS: dict[str, dict] = {
    "slack": {"name": "Slack", "scopes": ["chat:write"]},
    "jira": {"name": "Jira", "scopes": ["issues:write"]},
    "tracker": {"name": "Shipment tracker", "scopes": ["rows:write"]},
    "email": {"name": "Email inbox", "scopes": ["mail:read"]},
}
STATE_TTL = timedelta(minutes=10)


class MissingPermission(PermissionError):
    def __init__(self, app: str, scopes: list[str]):
        self.app, self.scopes = app, scopes
        super().__init__(f"{APPS.get(app, {}).get('name', app)} needs: {', '.join(scopes)}")


def apps_url() -> str:
    """Where the API reaches the (mock) apps; inside Docker that's http://mocksite:8081."""
    return os.getenv("MOCKSITE_URL", "http://localhost:8081").rstrip("/")


def public_apps_url() -> str:
    """Where the user's browser reaches the consent pages."""
    return os.getenv("MOCKSITE_PUBLIC_URL", "http://localhost:8081").rstrip("/")


def api_base() -> str:
    return os.getenv("API_BASE", "http://localhost:8000").rstrip("/")


def web_base() -> str:
    return os.getenv("WEB_BASE", "http://localhost:3000").rstrip("/")


def _http(method: str, url: str, body: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:200]
        raise ConnectionError(f"{method} {url} -> {err.code} {detail}") from err


async def http(method: str, url: str, body: dict | None = None, token: str | None = None) -> dict:
    return await asyncio.to_thread(_http, method, url, body, token)


def _doc_id(user_id: str, app: str) -> str:
    return f"{user_id}:{app}"


async def list_connectors(user_id: str) -> list[dict]:
    docs = {d["app"]: d async for d in deps.get_db().connectors.find({"user_id": user_id})}
    out = []
    for app, meta in APPS.items():
        doc = docs.get(app) or {}
        out.append(
            {
                "app": app,
                "name": meta["name"],
                "available_scopes": meta["scopes"],
                "status": doc.get("status", "not_connected"),
                "scopes": doc.get("scopes", []),
                "connected_at": doc.get("connected_at"),
            }
        )
    return out


async def granted(user_id: str) -> dict[str, list[str]]:
    """{app: scopes} for connected apps: what automation_plan() marks as granted."""
    return {
        d["app"]: d.get("scopes", [])
        async for d in deps.get_db().connectors.find({"user_id": user_id, "status": "connected"})
    }


async def start_connect(user_id: str, app: str, scopes: list[str] | None = None) -> dict:
    if app not in APPS:
        raise LookupError(f"unknown app {app}")
    scopes = scopes or APPS[app]["scopes"]
    unknown = [s for s in scopes if s not in APPS[app]["scopes"]]
    if unknown:
        raise ValueError(f"unknown scopes for {app}: {', '.join(unknown)}")
    state = "st_" + secrets.token_hex(8)
    await deps.get_db().connector_states.insert_one(
        {
            "_id": state,
            "user_id": user_id,
            "app": app,
            "scopes": scopes,
            "created_at": datetime.now(UTC),
        }
    )
    query = urlencode(
        {
            "app": app,
            "scopes": ",".join(scopes),
            "state": state,
            "redirect_uri": f"{api_base()}/connectors/callback",
        }
    )
    return {"consent_url": f"{public_apps_url()}/oauth/authorize?{query}", "state": state}


async def complete(state: str, code: str | None, error: str | None = None) -> dict:
    """Consent returned. Returns {app, status}; raises LookupError on an unknown/expired state."""
    db = deps.get_db()
    pending = await db.connector_states.find_one_and_delete({"_id": state})
    if not pending:
        raise LookupError("unknown or already used state")
    created = pending["created_at"]
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if datetime.now(UTC) - created > STATE_TTL:
        raise LookupError("consent took too long; start again")
    app = pending["app"]
    if error or not code:
        return {"app": app, "status": "denied"}
    token = await http("POST", f"{apps_url()}/oauth/token", {"code": code})
    now = datetime.now(UTC)
    _id = _doc_id(pending["user_id"], app)
    await db.connectors.update_one(
        {"_id": _id},
        {
            "$set": {
                "user_id": pending["user_id"],
                "app": app,
                "scopes": token.get("scopes", pending["scopes"]),
                "status": "connected",
                "connected_at": now,
                "token_ref": _id,
            }
        },
        upsert=True,
    )
    await db.connector_tokens.update_one(
        {"_id": _id}, {"$set": {"token": token["access_token"]}}, upsert=True
    )
    return {"app": app, "status": "connected"}


async def revoke(user_id: str, app: str) -> dict:
    _id = _doc_id(user_id, app)
    db = deps.get_db()
    res = await db.connectors.update_one(
        {"_id": _id}, {"$set": {"status": "revoked", "revoked_at": datetime.now(UTC)}}
    )
    await db.connector_tokens.delete_one({"_id": _id})
    return {"app": app, "status": "revoked" if res.matched_count else "not_connected"}


async def require(user_id: str, app: str, scopes: list[str]) -> str:
    """The token for `app` if every scope was granted; MissingPermission otherwise."""
    _id = _doc_id(user_id, app)
    db = deps.get_db()
    doc = await db.connectors.find_one({"_id": _id, "status": "connected"})
    missing = [s for s in scopes if s not in (doc or {}).get("scopes", [])]
    token = await db.connector_tokens.find_one({"_id": _id}) if not missing else None
    if missing or not token:
        raise MissingPermission(app, missing or scopes)
    return token["token"]
