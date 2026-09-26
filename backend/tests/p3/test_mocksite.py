import importlib.util
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

MOCKSITE = Path(__file__).resolve().parents[3] / "mocksite"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"mocksite_{name}", MOCKSITE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


server = load("server")
pytest.importorskip("bs4")
parse_v1 = load("parse_v1")
EXPECTED = json.loads(
    (MOCKSITE / "snapshots" / "expected_products.json").read_text(encoding="utf-8")
)


@pytest.fixture
def site():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    server.active["layout"] = "v1"
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    server.active["layout"] = "v1"


def get(url: str) -> str:
    with urllib.request.urlopen(url) as res:
        return res.read().decode()


def post(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, data=b"", method="POST")) as res:
        return json.loads(res.read())


def test_snapshots_match_live_render():
    for name in ("v1", "v2"):
        snapshot = (MOCKSITE / "snapshots" / f"products_{name}.html").read_text(encoding="utf-8")
        assert snapshot == server.render(name, "/products", {})[1]


def test_v1_parser_reads_v1_and_fails_on_v2():
    v1 = (MOCKSITE / "snapshots" / "products_v1.html").read_text(encoding="utf-8")
    v2 = (MOCKSITE / "snapshots" / "products_v2.html").read_text(encoding="utf-8")
    assert parse_v1.parse_products(v1) == EXPECTED
    assert parse_v1.parse_products(v2) == []  # the heal demo


def test_both_layouts_serve_and_switch(site):
    assert "Layout v1" in get(site + "/products")
    assert post(site + "/demo/mocksite/v2") == {"active": "v2"}
    html = get(site + "/products")
    assert "Layout v2" in html and 'class="item-card"' in html
    assert json.loads(get(site + "/demo/mocksite")) == {"active": "v2"}
    assert post(site + "/demo/mocksite/v1") == {"active": "v1"}


def test_pages_have_accessible_controls(site):
    for path in ("/products", "/products/PW-1001", "/report", "/search?q=kettle"):
        html = get(site + path)
        assert 'aria-label="Search products"' in html
        assert "<button" in html and "<label" in html


def test_api_proxies_layout_switch(site, monkeypatch):
    from app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MOCKSITE_URL", site)
    client = TestClient(app)
    assert client.post("/demo/mocksite/v2").json() == {"active": "v2"}
    assert "Layout v2" in get(site + "/products")
    assert client.get("/demo/mocksite").json() == {"active": "v2"}
    assert client.post("/demo/mocksite/v3").status_code == 400
