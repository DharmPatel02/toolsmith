# ruff: noqa: E501  (HTML templates)
"""Layout v1: list markup, `.price` after the name, SKU in `data-sku`."""

from html import escape


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{escape(title)} · PriceWatch</title>
<link rel="stylesheet" href="/static/v1.css"></head>
<body>
<header class="site-header"><a class="brand" href="/">PriceWatch</a>
<nav aria-label="Main"><a href="/products">Products</a> <a href="/report">Daily report</a></nav>
<form class="search" action="/search" method="get" role="search" aria-label="Search products">
<label for="q">Search</label><input id="q" name="q" type="search" placeholder="Product name">
<button type="submit">Search</button></form></header>
<main>{body}</main>
<footer>Layout v1</footer></body></html>"""


def product_list(products: list[dict], heading: str = "All products") -> str:
    rows = "\n".join(
        f"""<li class="product" data-sku="{p["sku"]}">
<h2 class="product-name"><a href="/products/{p["sku"]}">{escape(p["name"])}</a></h2>
<span class="vendor">{escape(p["vendor"])}</span>
<span class="price">${p["price"]:.2f}</span>
<span class="stock">{p["stock"]} in stock</span>
<button type="button" class="track" data-action="track" aria-label="Track {escape(p["name"])}">Track price</button>
</li>"""
        for p in products
    )
    return f'<h1>{escape(heading)}</h1>\n<ul class="product-list">\n{rows}\n</ul>'


def product_detail(p: dict) -> str:
    return f"""<article class="product-detail" data-sku="{p["sku"]}">
<h1 class="product-name">{escape(p["name"])}</h1>
<p class="vendor">Sold by {escape(p["vendor"])} · {escape(p["category"])}</p>
<p class="price">${p["price"]:.2f}</p>
<p class="stock">{p["stock"]} in stock</p>
<form method="post" action="/watchlist" aria-label="Add to watchlist">
<input type="hidden" name="sku" value="{p["sku"]}">
<label for="target">Alert below</label><input id="target" name="target" type="number" step="0.01">
<button type="submit">Add to watchlist</button></form>
<a href="/products">Back to products</a></article>"""


def report_form(saved: bool) -> str:
    note = '<p class="notice" role="status">Report saved.</p>' if saved else ""
    return f"""<h1>Daily price report</h1>{note}
<form method="post" action="/report" aria-label="Save daily report">
<label for="notes">Notes</label><textarea id="notes" name="notes" rows="3"></textarea>
<button type="submit">Save report</button></form>"""
