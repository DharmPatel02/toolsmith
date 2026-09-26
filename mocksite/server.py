"""PriceWatch mock site for the UC3 scrape/heal demo. Stdlib only (runs in a bare python image).

Same data in two layouts; `POST /demo/mocksite/{v1|v2}` flips the active one. Port 8081 by default.
    python mocksite/server.py [--port 8081] [--layout v1]
    python mocksite/server.py --snapshot     # rewrite snapshots/ (UC3 replay fixtures)
"""

import argparse
import importlib.util
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
PRODUCTS = json.loads((HERE / "products.json").read_text(encoding="utf-8"))
BY_SKU = {p["sku"]: p for p in PRODUCTS}
LAYOUT_NAMES = ("v1", "v2")


def _load_layout(name: str):
    spec = importlib.util.spec_from_file_location(f"layout_{name}", HERE / name / "layout.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LAYOUTS = {name: _load_layout(name) for name in LAYOUT_NAMES}
active = {"layout": os.environ.get("MOCKSITE_LAYOUT", "v1")}


def render(layout_name: str, path: str, query: dict) -> tuple[int, str]:
    """Returns (status, html) for a GET path in the given layout."""
    layout = LAYOUTS[layout_name]
    if path in ("/", "/products"):
        category = query.get("category", [""])[0]
        items = [p for p in PRODUCTS if not category or p["category"] == category]
        return 200, layout.page(
            "Products", layout.product_list(items, f"{category or 'All'} products")
        )
    if path == "/search":
        q = query.get("q", [""])[0].strip().lower()
        items = [p for p in PRODUCTS if q in p["name"].lower()]
        return 200, layout.page("Search", layout.product_list(items, f'Results for "{q}"'))
    if path.startswith("/products/"):
        product = BY_SKU.get(path.removeprefix("/products/"))
        if product:
            return 200, layout.page(product["name"], layout.product_detail(product))
    if path == "/report":
        return 200, layout.page("Daily report", layout.report_form("saved" in query))
    return 404, layout.page("Not found", "<h1>Not found</h1>")


class Handler(BaseHTTPRequestHandler):
    def _send(
        self,
        status: int,
        body: str | bytes,
        content_type: str = "text/html; charset=utf-8",
        headers=None,
    ):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: dict):
        self._send(status, json.dumps(payload), "application/json")

    def do_OPTIONS(self):
        self._send(
            204,
            b"",
            headers={
                "Access-Control-Allow-Methods": "GET, POST",
                "Access-Control-Allow-Headers": "Content-Type",
            },
        )

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/demo/mocksite":
            return self._json(200, {"active": active["layout"]})
        if url.path.startswith("/static/"):
            name = url.path.removeprefix("/static/")
            css = HERE / name.removesuffix(".css") / name if name in ("v1.css", "v2.css") else None
            if css and css.exists():
                return self._send(200, css.read_bytes(), "text/css")
            return self._send(404, "not found", "text/plain")
        status, html = render(active["layout"], url.path, parse_qs(url.query))
        self._send(status, html)

    def do_POST(self):
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)  # form bodies are accepted and discarded
        if url.path.startswith("/demo/mocksite/"):
            layout = url.path.removeprefix("/demo/mocksite/")
            if layout not in LAYOUT_NAMES:
                return self._json(400, {"detail": f"layout must be one of {LAYOUT_NAMES}"})
            active["layout"] = layout
            return self._json(200, {"active": layout})
        if url.path == "/report":
            return self._send(303, b"", headers={"Location": "/report?saved=1"})
        if url.path == "/watchlist":
            return self._send(303, b"", headers={"Location": "/products?watched=1"})
        self._send(404, "not found", "text/plain")

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[mocksite {active['layout']}] {fmt % args}\n")


def write_snapshots():
    """Cached HTML for the UC3 replay gate: products page in both layouts.
    Also written to data/artifacts/uc3/{v1,v2}.html, where P2's UC3 seed and heal read them."""
    out = HERE / "snapshots"
    artifacts = HERE.parent / "data" / "artifacts" / "uc3"
    out.mkdir(exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    for name in LAYOUT_NAMES:
        html = render(name, "/products", {})[1]
        (out / f"products_{name}.html").write_text(html, encoding="utf-8")
        (artifacts / f"{name}.html").write_text(html, encoding="utf-8")
    print(f"wrote {out} and {artifacts}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("MOCKSITE_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MOCKSITE_PORT", 8081)))
    parser.add_argument("--layout", choices=LAYOUT_NAMES)
    parser.add_argument("--snapshot", action="store_true")
    args = parser.parse_args()
    if args.snapshot:
        return write_snapshots()
    if args.layout:
        active["layout"] = args.layout
    print(f"PriceWatch mock site on http://localhost:{args.port} (layout {active['layout']})")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
