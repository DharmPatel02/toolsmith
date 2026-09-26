# ruff: noqa: E501  (HTML templates)
"""Layout v2: same data, different structure. Grid of cards, renamed classes, price moved above the
title and wrapped in `.item-meta`, SKU in `data-id`. A v1 parser finds nothing here (heal demo)."""

from html import escape


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{escape(title)} · PriceWatch</title>
<link rel="stylesheet" href="/static/v2.css"></head>
<body>
<div class="topbar"><a class="logo" href="/">PriceWatch</a>
<form class="finder" action="/search" method="get" role="search" aria-label="Search products">
<label for="q">Find</label><input id="q" name="q" type="search" placeholder="What are you looking for?">
<button type="submit">Search</button></form>
<nav aria-label="Main"><a href="/products">Catalog</a> <a href="/report">Daily report</a></nav></div>
<section class="content">{body}</section>
<footer>Layout v2</footer></body></html>"""


def product_list(products: list[dict], heading: str = "All products") -> str:
    cards = "\n".join(
        f"""<article class="item-card" data-id="{p["sku"]}">
<div class="item-meta"><span class="item-price">USD {p["price"]:.2f}</span><span class="item-stock">{p["stock"]} left</span></div>
<h3 class="item-title"><a href="/products/{p["sku"]}">{escape(p["name"])}</a></h3>
<small class="item-seller">{escape(p["vendor"])}</small>
<button type="button" class="watch-btn" data-action="track" aria-label="Track {escape(p["name"])}">Track price</button>
</article>"""
        for p in products
    )
    return f'<h2 class="section-title">{escape(heading)}</h2>\n<div class="catalog-grid">\n{cards}\n</div>'


def product_detail(p: dict) -> str:
    return f"""<div class="item-page" data-id="{p["sku"]}">
<div class="item-meta"><span class="item-price">USD {p["price"]:.2f}</span></div>
<h2 class="item-title">{escape(p["name"])}</h2>
<p class="item-seller">{escape(p["vendor"])} / {escape(p["category"])} / {p["stock"]} left</p>
<form method="post" action="/watchlist" aria-label="Add to watchlist">
<input type="hidden" name="sku" value="{p["sku"]}">
<label for="target">Alert below</label><input id="target" name="target" type="number" step="0.01">
<button type="submit">Add to watchlist</button></form>
<a href="/products">Back to catalog</a></div>"""


def report_form(saved: bool) -> str:
    note = '<div class="toast" role="status">Report saved.</div>' if saved else ""
    return f"""<h2 class="section-title">Daily price report</h2>{note}
<form method="post" action="/report" aria-label="Save daily report">
<label for="notes">Notes</label><textarea id="notes" name="notes" rows="3"></textarea>
<button type="submit">Save report</button></form>"""
