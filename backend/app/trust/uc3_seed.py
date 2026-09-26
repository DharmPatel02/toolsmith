"""UC3 seed (TASKS §4.1: "UC3 is seeded as an already-promoted tool"): the mock-site price
scraper that breaks when the site flips to v2, so heal has something to fix.

`seed_uc3_tool(user_id)` writes the tool + v1 version + a run history (supervised, baseline
success rate 1.0). Idempotent. P1's demo_reset calls it.

Markup contract with P3's mock site (§8 request): v1 lists `li.product` with `.product-name`
and `.price`; v2 has the same data with renamed classes and the price moved. The reference
pages below follow it and are used when P3's snapshots (data/artifacts/uc3/v1.html, v2.html)
aren't there.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app import embeddings
from app.forge import deps
from app.forge.spec import REPO_ROOT
from app.sandbox import run_in_sandbox
from app.sandbox.harness import FETCH_MAP_INPUT

TOOL_ID = "tool_uc3_prices"
NAME = "mocksite_price_watch"
SNAPSHOT_DIR = REPO_ROOT / "data" / "artifacts" / "uc3"

UC3_V1_CODE = '''\
from bs4 import BeautifulSoup


def run(ctx, url):
    html = ctx.fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for item in soup.select("li.product"):
        name = item.select_one(".product-name").get_text(strip=True)
        price = item.select_one(".price").get_text(strip=True)
        rows.append({"name": name, "price": round(float(price.replace("$", "").replace(",", "")), 2)})
    if not rows:
        raise ValueError("no products found on the page")
    rows.sort(key=lambda r: r["name"])
    cheapest = min(rows, key=lambda r: r["price"])
    return {"summary": f"{len(rows)} products, cheapest {cheapest['name']} at ${cheapest['price']:.2f}",
            "tables": {"products": rows}}
'''

UC3_V1_TESTS = '''\
PAGE = ('<ul><li class="product"><span class="product-name">B</span><span class="price">$2.50</span></li>'
        '<li class="product"><span class="product-name">A</span><span class="price">$1,001.00</span></li></ul>')


def test_parses_and_sorts():
    out = run(FakeCtx(pages={"http://x/": PAGE}), url="http://x/")
    assert out["tables"]["products"] == [{"name": "A", "price": 1001.0}, {"name": "B", "price": 2.5}]


def test_empty_page_fails():
    try:
        run(FakeCtx(pages={"http://x/": "<html></html>"}), url="http://x/")
    except ValueError:
        return
    raise AssertionError("expected ValueError")
'''

PRODUCTS = [("Desk Lamp", "24.99"), ("Ergo Chair", "189.00"), ("Monitor Arm", "59.50"),
            ("USB-C Hub", "34.90"), ("Webcam HD", "72.00"), ("Wireless Mouse", "19.99")]

REFERENCE_V1_HTML = (
    "<!doctype html><html><head><title>Shop</title></head><body><h1>Products</h1>"
    "<form role='search'><input name='q' aria-label='Search'><button>Search</button></form><ul id='products'>"
    + "".join(f"<li class='product'><span class='product-name'>{n}</span><span class='price'>${p}</span></li>"
              for n, p in PRODUCTS)
    + "</ul></body></html>")

REFERENCE_V2_HTML = (
    "<!doctype html><html><head><title>Shop</title></head><body><h1>Products</h1>"
    "<form role='search'><input name='q' aria-label='Search'><button>Search</button></form><div class='catalog'>"
    + "".join(f"<article class='card'><div class='card-price'>${p}</div><h3 class='card-title'>{n}</h3></article>"
              for n, p in PRODUCTS)
    + "</div></body></html>")

SPEC = {
    "name": NAME, "title": "Mock-site price watch",
    "purpose": "Reads the shop's product list and returns every product with its price, cheapest first in the summary.",
    "params_schema": {"type": "object", "properties": {"url": {"type": "string", "description": "shop page URL"}},
                      "required": ["url"]},
    "outputs": {"tables": ["products"], "chart": False, "files": []},
    "requires": {"scopes": [], "deps": ["bs4"], "tools": []},
    "keywords": ["prices", "scrape", "shop", "products", "watch"],
    "derivation": {"observed_tier": "T1", "execution_path": "browser"},
    "not_automatable": None,
}

TUTORIAL = """# Mock-site price watch

## What it does
Reads the shop page and lists every product with its price, so you don't copy prices by hand each morning.

## What you give it
The shop page address (url), for example the mock site's home page.

## What you get back
A products table (name, price) and a one-line summary naming the cheapest product.

## Example
Run on the shop home page: 6 products, cheapest Wireless Mouse at $19.99.

## Limits
Needs network access to the shop's domain only. If the page layout changes the tool fails, and ToolSmith heals it.
"""


def shop_url() -> str:
    return os.getenv("MOCKSITE_URL", "http://localhost:8081").rstrip("/") + "/"


def net_scope(url: str) -> str:
    from urllib.parse import urlparse

    return f"net:{urlparse(url).hostname}"


def snapshot(version: str) -> str:
    """P3's saved page if present, else the reference page with the agreed markup."""
    p = SNAPSHOT_DIR / f"{version}.html"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return REFERENCE_V1_HTML if version == "v1" else REFERENCE_V2_HTML


def replay_case(label: str, url: str, html: str, expected_rows: list[dict] | None) -> dict:
    return {"label": label, "inputs": {FETCH_MAP_INPUT: json.dumps({url: html})}, "params": {"url": url},
            "expected": {"tables": {"products": expected_rows} if expected_rows is not None else {}, "chart": None}}


async def seed_uc3_tool(user_id: str, runs: int = 12) -> str:
    db = deps.get_db()
    url = shop_url()
    scopes = [net_scope(url)]
    v1_html = snapshot("v1")
    ref = await run_in_sandbox(UC3_V1_CODE, "run", {"url": url}, {FETCH_MAP_INPUT: json.dumps({url: v1_html})},
                               "dry_run", scopes)
    if not ref.ok:
        raise RuntimeError(f"UC3 v1 scraper does not parse the v1 page: {ref.error}")
    rows = ref.output["tables"]["products"]
    spec = {**SPEC, "requires": {**SPEC["requires"], "scopes": scopes},
            "params_schema": {**SPEC["params_schema"], "properties": {"url": {"type": "string", "default": url}}}}
    now = datetime.now(UTC)
    vec = (await embeddings.embed([f"{spec['title']}\n{spec['purpose']}\n{', '.join(spec['keywords'])}"]))[0]
    await db.tool_versions.replace_one({"_id": f"{TOOL_ID}@v1"}, {
        "_id": f"{TOOL_ID}@v1", "tool_id": TOOL_ID, "user_id": user_id, "version": 1,
        "code": UC3_V1_CODE, "tests": UC3_V1_TESTS, "params_schema": spec["params_schema"], "spec": spec,
        "tutorial_md": TUTORIAL, "requires": spec["requires"], "derivation": spec["derivation"],
        "fixtures_ref": {"replay_cases": [replay_case("mocksite_v1", url, v1_html, rows)]},
        "created_from": {"seed": "uc3"}, "verdict_id": None, "approved_at": now - timedelta(days=14)}, upsert=True)
    await db.tools.replace_one({"_id": TOOL_ID}, {
        "_id": TOOL_ID, "user_id": user_id, "name": NAME, "title": spec["title"], "status": "active",
        "trust": "supervised", "active_version": 1, "keywords": spec["keywords"], "embedding": vec,
        "embedding_model": embeddings.text_model(), "tier": "lean", "derivation": spec["derivation"],
        "created_at": now - timedelta(days=14), "updated_at": now,
        "stats": {"runs": runs, "success": runs, "edited": 0, "p50_ms": 900, "minutes_saved": runs * 4},
        "baseline": {"success_rate": 1.0, "window": 10}, "trust_history": [], "trust_streak": runs,
        "lineage": {"calls": [], "parents": [], "merged_from": [], "merged_into": None}}, upsert=True)
    await db.runs.delete_many({"tool_id": TOOL_ID})
    if runs:
        await db.runs.insert_many([{
            "_id": f"run_uc3_{i:02d}", "tool_id": TOOL_ID, "user_id": user_id, "version": 1, "mode": "live",
            "params": {"url": url}, "outcome": "success", "ok": True, "duration_ms": 900,
            "started_at": now - timedelta(days=runs - i)} for i in range(runs)])
    return TOOL_ID
