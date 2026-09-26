# ruff: noqa: E501  (HTML templates)
"""Mock third-party apps for the demo (stdlib only): Slack, Jira, a shipment/invoice tracker, an
email inbox, a second competitor shop, and an OAuth-style consent flow that issues scoped tokens.

ToolSmith's connectors call the JSON APIs with a bearer token; the HTML pages auto-refresh so the
audience sees messages, tickets and tracker rows appear (and disappear on undo) live.

    /oauth/authorize?app=slack&scopes=chat:write&redirect_uri=...&state=...   consent page
    POST /oauth/token {"code"} -> {"access_token", "app", "scopes"}
    GET/POST/DELETE /api/slack/messages[/<id>]     scope chat:write
    GET/POST/DELETE /api/jira/issues[/<key>]       scope issues:write
    GET/POST/DELETE /api/tracker/rows[/<id>]       scope rows:write   (POST upserts by `ref`)
    GET /api/inbox, GET /api/inbox/<id>/attachment scope mail:read;  POST /api/inbox/send-test
    POST /apps/reset                               clears everything (demo_reset)
"""

from __future__ import annotations

import html
import itertools
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
INVOICES = HERE.parent / "data" / "artifacts" / "uc2_invoices"

APPS = {
    "slack": {"name": "Slack", "scopes": {"chat:write": "Post messages to channels you choose"}},
    "jira": {"name": "Jira", "scopes": {"issues:write": "Create and delete issues in project WH"}},
    "tracker": {"name": "Shipment tracker", "scopes": {"rows:write": "Add, update and remove tracker rows"}},
    "email": {"name": "Email inbox", "scopes": {"mail:read": "Read invoices in your inbox"}},
}
API_SCOPE = {"slack": "chat:write", "jira": "issues:write", "tracker": "rows:write", "inbox": "mail:read"}

state: dict = {}
_ids = itertools.count(1)


def reset() -> None:
    state.clear()
    state.update(slack=[], jira=[], tracker=[], inbox=_initial_inbox(), codes={}, tokens={})


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _initial_inbox() -> list[dict]:
    manifest = INVOICES / "manifest.json"
    if not manifest.exists():
        return []
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    return [dict(r, read=False) for r in rows if not r.get("test")]


reset()


# ---- helpers --------------------------------------------------------------------------------

def _token_ok(headers, app: str) -> bool:
    auth = headers.get("Authorization", "")
    token = state["tokens"].get(auth.removeprefix("Bearer ").strip())
    needed = API_SCOPE[app]
    oauth_app = "email" if app == "inbox" else app
    return bool(token) and token["app"] == oauth_app and needed in token["scopes"]


def _page(title: str, body: str, refresh: bool = True) -> str:
    meta = '<meta http-equiv="refresh" content="2">' if refresh else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">{meta}<title>{html.escape(title)}</title>
<style>body{{font-family:system-ui,sans-serif;margin:0;background:#f6f6f4;color:#111}}header{{background:#1f1f1f;color:#fff;padding:10px 20px;font-weight:600}}
main{{max-width:900px;margin:20px auto;padding:0 16px}}.card{{background:#fff;border:1px solid #e3e3df;border-radius:10px;padding:12px 14px;margin-bottom:10px}}
.muted{{color:#6b6b66;font-size:13px}}table{{width:100%;border-collapse:collapse;background:#fff}}td,th{{border-bottom:1px solid #eee;padding:8px;text-align:left;font-size:14px}}
.tag{{display:inline-block;padding:2px 8px;border-radius:99px;background:#eee;font-size:12px}}.bad{{background:#fde2e1;color:#8a1c1b}}.ok{{background:#dff3e4;color:#1d5c2e}}
button{{padding:8px 14px;border-radius:8px;border:1px solid #111;background:#111;color:#fff;cursor:pointer}}button.secondary{{background:#fff;color:#111}}</style></head>
<body><header>{html.escape(title)}</header><main>{body}</main></body></html>"""


def _empty(text: str) -> str:
    return f'<p class="muted">{html.escape(text)}</p>'


# ---- HTML views ------------------------------------------------------------------------------

def slack_page() -> str:
    msgs = "".join(
        f'<div class="card"><b>{html.escape(m["channel"])}</b> <span class="muted">ToolSmith · {m["ts"]}</span><div>{html.escape(m["text"])}</div></div>'
        for m in reversed(state["slack"])
    )
    return _page("Slack (mock)", msgs or _empty("No messages yet."))


def jira_page() -> str:
    cards = "".join(
        f'<div class="card"><b>{i["key"]}</b> <span class="tag">{html.escape(i["status"])}</span> {html.escape(i["summary"])}<div class="muted">{html.escape(i.get("description", ""))}</div></div>'
        for i in reversed(state["jira"])
    )
    return _page("Jira · project WH (mock)", cards or _empty("No issues."))


def tracker_page() -> str:
    rows = "".join(
        f'<tr><td>{html.escape(r["ref"])}</td><td>{html.escape(r.get("vendor", ""))}</td><td>{html.escape(str(r.get("amount", "")))}</td>'
        f'<td><span class="tag {"bad" if r.get("status") == "mismatch" else "ok"}">{html.escape(r.get("status", ""))}</span></td>'
        f'<td class="muted">{html.escape(r.get("note", ""))}</td><td class="muted">{r["updated"]}</td></tr>'
        for r in state["tracker"]
    )
    table = f"<table><tr><th>Ref</th><th>Vendor</th><th>Amount</th><th>Status</th><th>Note</th><th>Updated</th></tr>{rows}</table>"
    return _page("Shipment & invoice tracker (mock)", table if rows else _empty("Tracker is empty."))


def inbox_page() -> str:
    mails = "".join(
        f'<div class="card"><b>{html.escape(m["subject"])}</b> <span class="muted">from {html.escape(m["from"])} · {m["received"]}</span>'
        f'<div class="muted">attachment: <a href="/api/inbox/{m["id"]}/attachment/view">{html.escape(m["attachment"])}</a></div></div>'
        for m in reversed(state["inbox"])
    )
    form = '<form method="post" action="/apps/inbox/send-test"><button type="submit">Send test invoice</button></form><br>'
    return _page("Inbox · ap@warehouse.example (mock)", form + (mails or _empty("Inbox is empty.")))


def consent_page(query: dict) -> tuple[int, str]:
    app = query.get("app", [""])[0]
    if app not in APPS:
        return 400, _page("Unknown app", _empty(f"No such app: {app}"), refresh=False)
    scopes = [s for s in query.get("scopes", [""])[0].split(",") if s] or list(APPS[app]["scopes"])
    unknown = [s for s in scopes if s not in APPS[app]["scopes"]]
    if unknown:
        return 400, _page("Unknown scope", _empty(f"Unknown scopes: {', '.join(unknown)}"), refresh=False)
    items = "".join(f"<li><b>{html.escape(s)}</b> · {html.escape(APPS[app]['scopes'][s])}</li>" for s in scopes)
    hidden = "".join(
        f'<input type="hidden" name="{k}" value="{html.escape(query.get(k, [""])[0])}">'
        for k in ("app", "redirect_uri", "state")
    ) + f'<input type="hidden" name="scopes" value="{html.escape(",".join(scopes))}">'
    body = f"""<div class="card"><h2>ToolSmith wants to access your {APPS[app]["name"]} account</h2>
<p>It will be able to:</p><ul>{items}</ul><p class="muted">You can revoke this at any time from ToolSmith → Connected apps.</p>
<form method="post" action="/oauth/decide">{hidden}<button name="decision" value="allow" type="submit">Allow</button>
<button class="secondary" name="decision" value="deny" type="submit">Deny</button></form></div>"""
    return 200, _page(f"{APPS[app]['name']} · authorize ToolSmith", body, refresh=False)


# ---- request handling ------------------------------------------------------------------------

def handle(method: str, path: str, query: dict, body: bytes, headers) -> tuple[int, str | bytes, str, dict] | None:
    """Returns (status, body, content_type, extra_headers), or None if the path isn't an app route."""
    views = {"/apps/slack": slack_page, "/apps/jira": jira_page, "/apps/tracker": tracker_page, "/apps/inbox": inbox_page}
    if method == "GET" and path in views:
        return 200, views[path](), "text/html; charset=utf-8", {}
    if method == "GET" and path == "/oauth/authorize":
        status, page = consent_page(query)
        return status, page, "text/html; charset=utf-8", {}
    if method == "POST" and path == "/oauth/decide":
        return _decide(body)
    if method == "POST" and path == "/oauth/token":
        return _token(body)
    if method == "POST" and path == "/apps/reset":
        reset()
        return _json(200, {"ok": True})
    if method == "POST" and path in ("/api/inbox/send-test", "/apps/inbox/send-test"):
        mail = _send_test()
        if path.startswith("/apps/"):
            return 303, b"", "text/plain", {"Location": "/apps/inbox"}
        return _json(201, mail)
    if path.startswith("/api/"):
        return _api(method, path, body, headers)
    return None


def _json(status: int, payload) -> tuple[int, str, str, dict]:
    return status, json.dumps(payload), "application/json", {}


def _form(body: bytes) -> dict:
    from urllib.parse import parse_qs

    return {k: v[0] for k, v in parse_qs(body.decode()).items()}


def _decide(body: bytes):
    f = _form(body)
    redirect = f.get("redirect_uri", "")
    if not redirect.startswith(("http://localhost", "http://127.0.0.1")):
        return _json(400, {"detail": "redirect_uri must be a local ToolSmith URL"})
    sep = "&" if "?" in redirect else "?"
    if f.get("decision") != "allow":
        return 303, b"", "text/plain", {"Location": redirect + sep + urlencode({"error": "access_denied", "state": f.get("state", ""), "app": f.get("app", "")})}
    code = "code_" + secrets.token_hex(8)
    state["codes"][code] = {"app": f["app"], "scopes": f.get("scopes", "").split(",")}
    return 303, b"", "text/plain", {"Location": redirect + sep + urlencode({"code": code, "state": f.get("state", ""), "app": f["app"]})}


def _token(body: bytes):
    try:
        code = json.loads(body or b"{}").get("code", "")
    except json.JSONDecodeError:
        code = ""
    grant = state["codes"].pop(code, None)
    if not grant:
        return _json(400, {"detail": "invalid or used code"})
    token = "tok_" + secrets.token_hex(12)
    state["tokens"][token] = grant
    return _json(200, {"access_token": token, **grant})


def _send_test() -> dict:
    manifest = INVOICES / "manifest.json"
    rows = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    template = next((r for r in rows if r.get("test")), None) or {"subject": "Invoice", "from": "billing@vendor.example", "attachment": "missing.pdf"}
    mail = dict(template, id=f"m{next(_ids)}", received=_now(), read=False)
    state["inbox"].append(mail)
    return mail


def _api(method: str, path: str, body: bytes, headers):
    parts = path.strip("/").split("/")  # api, app, collection, [id], [attachment]
    app = parts[1] if len(parts) > 1 else ""
    if app not in API_SCOPE:
        return _json(404, {"detail": "unknown app"})
    store = {"slack": "slack", "jira": "jira", "tracker": "tracker", "inbox": "inbox"}[app]
    if method == "GET" and len(parts) == 3:
        return _json(200, state[store])
    # /api/inbox/<id>/attachment (API, needs mail:read) or .../attachment/view (the page's own link)
    if app == "inbox" and method == "GET" and len(parts) >= 4 and parts[3] == "attachment":
        mail = next((m for m in state["inbox"] if m["id"] == parts[2]), None)
        if mail is None:
            return _json(404, {"detail": "no such email"})
        if len(parts) == 4 and not _token_ok(headers, "inbox"):
            return _json(401, {"detail": "token with mail:read required"})
        pdf = INVOICES / mail["attachment"]
        if not pdf.exists():
            return _json(404, {"detail": "attachment missing"})
        return 200, pdf.read_bytes(), "application/pdf", {}
    if not _token_ok(headers, app):
        return _json(401, {"detail": f"token with {API_SCOPE[app]} required"})
    try:
        data = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return _json(400, {"detail": "invalid JSON"})
    items = state[store]
    if method == "POST" and len(parts) == 3:
        if app == "slack":
            item = {"id": f"msg{next(_ids)}", "channel": data.get("channel", "#general"), "text": data.get("text", ""), "ts": _now()}
        elif app == "jira":
            item = {"key": f"WH-{next(_ids)}", "summary": data.get("summary", ""), "description": data.get("description", ""), "status": "To Do"}
        else:  # tracker upsert by ref
            ref = data.get("ref") or f"row{next(_ids)}"
            existing = next((r for r in items if r["ref"] == ref), None)
            fields = {k: data[k] for k in ("vendor", "amount", "status", "note") if k in data}
            if existing:
                previous = {k: existing.get(k) for k in fields}
                existing.update(fields, updated=_now())
                return _json(200, {**existing, "created": False, "previous": previous})
            item = {"id": f"row{next(_ids)}", "ref": ref, **fields, "updated": _now()}
        items.append(item)
        return _json(201, {**item, "created": True})
    if method == "DELETE" and len(parts) == 4:
        key = "key" if app == "jira" else "id"
        before = len(items)
        items[:] = [i for i in items if i.get(key) != parts[3]]
        return _json(200 if len(items) < before else 404, {"deleted": len(items) < before})
    if method == "PATCH" and len(parts) == 4 and app == "tracker":
        row = next((r for r in items if r["id"] == parts[3]), None)
        if not row:
            return _json(404, {"detail": "no such row"})
        row.update({k: v for k, v in data.items() if k in ("vendor", "amount", "status", "note")}, updated=_now())
        return _json(200, row)
    return _json(405, {"detail": "method not allowed"})
