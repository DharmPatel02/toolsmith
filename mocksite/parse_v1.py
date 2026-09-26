"""Reference UC3 parser written against layout v1, like a tool forged from the v1 site.
On v2 it finds no products: the drift the heal loop repairs. Used by tests and the gate."""

from bs4 import BeautifulSoup


def parse_products(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for li in soup.select("ul.product-list li.product"):
        rows.append(
            {
                "sku": li["data-sku"],
                "name": li.select_one(".product-name").get_text(strip=True),
                "price": float(li.select_one(".price").get_text(strip=True).lstrip("$")),
            }
        )
    return rows
