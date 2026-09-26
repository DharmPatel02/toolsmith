"""Mock apps + OAuth consent on the mock site (mocksite/apps.py)."""

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import pytest

MOCKSITE = Path(__file__).resolve().parents[3] / "mocksite"
spec = importlib.util.spec_from_file_location("mocksite_server_apps", MOCKSITE / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@pytest.fixture
def site():
    server.apps.reset()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def call(url, method="GET", data=None, token=None, form=False):
    headers = {}
    body = None
    if data is not None:
        body = urlencode(data).encode() if form else json.dumps(data).encode()
        headers["Content-Type"] = (
            "application/x-www-form-urlencoded" if form else "application/json"
        )
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req) as res:
            return res.status, res.headers, res.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers, err.read()


def grant(site, app, scopes, decision="allow"):
    """Walks the consent flow like a browser: consent -> Allow -> redirect with code -> token."""
    status, _, page = call(
        f"{site}/oauth/authorize?app={app}&scopes={scopes}"
        f"&redirect_uri=http://localhost:3000/connectors&state=s1"
    )
    assert status == 200 and b"ToolSmith wants to access your" in page
    status, headers, _ = call(
        f"{site}/oauth/decide",
        "POST",
        {
            "app": app,
            "scopes": scopes,
            "redirect_uri": "http://localhost:3000/connectors",
            "state": "s1",
            "decision": decision,
        },
        form=True,
    )
    assert status == 303
    query = parse_qs(urlparse(headers["Location"]).query)
    assert query["state"] == ["s1"]
    if decision != "allow":
        return query
    status, _, body = call(f"{site}/oauth/token", "POST", {"code": query["code"][0]})
    assert status == 200
    return json.loads(body)


def test_consent_allow_issues_scoped_token_once(site):
    token = grant(site, "slack", "chat:write")
    assert token["app"] == "slack" and token["scopes"] == ["chat:write"]
    assert token["access_token"].startswith("tok_")


def test_consent_deny_and_bad_inputs(site):
    assert grant(site, "jira", "issues:write", decision="deny")["error"] == ["access_denied"]
    assert call(f"{site}/oauth/authorize?app=github")[0] == 400
    assert call(f"{site}/oauth/authorize?app=slack&scopes=admin")[0] == 400
    assert call(f"{site}/oauth/token", "POST", {"code": "nope"})[0] == 400
    status, _, _ = call(
        f"{site}/oauth/decide",
        "POST",
        {"app": "slack", "redirect_uri": "https://evil.example/", "decision": "allow"},
        form=True,
    )
    assert status == 400


def test_apis_require_the_right_token(site):
    assert call(f"{site}/api/slack/messages", "POST", {"text": "x"})[0] == 401
    jira = grant(site, "jira", "issues:write")["access_token"]
    assert call(f"{site}/api/slack/messages", "POST", {"text": "x"}, token=jira)[0] == 401


def test_slack_jira_post_and_delete_show_on_pages(site):
    slack = grant(site, "slack", "chat:write")["access_token"]
    status, _, body = call(
        f"{site}/api/slack/messages",
        "POST",
        {"channel": "#pricing", "text": "Kettle is 15% cheaper at ShopB"},
        token=slack,
    )
    msg = json.loads(body)
    assert status == 201 and b"15% cheaper" in call(f"{site}/apps/slack")[2]
    assert call(f"{site}/api/slack/messages/{msg['id']}", "DELETE", token=slack)[0] == 200
    assert b"15% cheaper" not in call(f"{site}/apps/slack")[2]

    jira = grant(site, "jira", "issues:write")["access_token"]
    issue = json.loads(
        call(f"{site}/api/jira/issues", "POST", {"summary": "INV-2202 qty over PO"}, token=jira)[2]
    )
    assert (
        issue["key"].startswith("WH-") and b"INV-2202 qty over PO" in call(f"{site}/apps/jira")[2]
    )


def test_tracker_upserts_by_ref(site):
    token = grant(site, "tracker", "rows:write")["access_token"]
    first = json.loads(
        call(
            f"{site}/api/tracker/rows",
            "POST",
            {"ref": "INV-2202", "status": "received", "amount": 665.25},
            token=token,
        )[2]
    )
    again = json.loads(
        call(
            f"{site}/api/tracker/rows",
            "POST",
            {"ref": "INV-2202", "status": "mismatch"},
            token=token,
        )[2]
    )
    assert first["created"] and not again["created"]
    assert again["previous"] == {"status": "received"}  # what undo restores
    assert len(json.loads(call(f"{site}/api/tracker/rows")[2])) == 1


def test_inbox_lists_invoices_and_send_test_adds_one(site):
    inbox = json.loads(call(f"{site}/api/inbox/messages")[2])
    assert len(inbox) == 6 and all(m["attachment"].endswith(".pdf") for m in inbox)
    assert call(f"{site}/api/inbox/{inbox[0]['id']}/attachment")[0] == 401  # needs mail:read
    token = grant(site, "email", "mail:read")["access_token"]
    status, headers, pdf = call(f"{site}/api/inbox/{inbox[0]['id']}/attachment", token=token)
    assert status == 200 and pdf.startswith(b"%PDF")
    status, _, body = call(f"{site}/api/inbox/send-test", "POST", {})
    assert status == 201 and json.loads(body)["invoice"] == "INV-2207"
    assert len(json.loads(call(f"{site}/api/inbox/messages")[2])) == 7


def test_competitor_b_has_same_markup_different_prices(site):
    import sys

    sys.path.insert(0, str(MOCKSITE))
    from parse_v1 import parse_products

    ours = {p["sku"]: p["price"] for p in parse_products(call(f"{site}/products")[2].decode())}
    theirs = {
        p["sku"]: p["price"]
        for p in parse_products(call(f"{site}/competitor-b/products")[2].decode())
    }
    assert ours.keys() == theirs.keys() and ours != theirs
