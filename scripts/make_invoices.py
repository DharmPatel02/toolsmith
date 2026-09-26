"""UC2 synthetic data: purchase orders + vendor invoices (PDF) for the invoice-to-tracker demo.

Writes data/artifacts/uc2_invoices/:
  po.xlsx            purchase orders (po_number, vendor, sku, description, qty, unit_price)
  inv_<n>.pdf        6 history invoices (2 with a mismatch) + 1 live test invoice (qty mismatch)
  manifest.json      inbox emails (subject, from, attachment, received) read by the mock inbox
  expected/<n>.json  what a correct tool must report per invoice
  expected/<n>_issues.csv  the same issues as the replay gate's expected table

Deterministic: same files every run.   python scripts/make_invoices.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "artifacts" / "uc2_invoices"

VENDORS = {
    "Northwind Supplies": "billing@northwind.example",
    "Acme Packaging": "ar@acme-packaging.example",
    "BlueRiver Logistics": "invoices@blueriver.example",
}
# po_number -> (vendor, [(sku, description, qty, unit_price)])
POS = {
    "PO-4101": (
        "Northwind Supplies",
        [("NW-100", "Pallet wrap 500mm", 40, 18.50), ("NW-210", "Corner boards", 200, 0.65)],
    ),
    "PO-4102": (
        "Acme Packaging",
        [("AC-12", "Shipping box L", 300, 1.20), ("AC-14", "Shipping box XL", 150, 1.85)],
    ),
    "PO-4103": ("BlueRiver Logistics", [("BR-FRT", "Freight Chicago-Dallas", 1, 2450.00)]),
    "PO-4104": ("Northwind Supplies", [("NW-100", "Pallet wrap 500mm", 25, 18.50)]),
    "PO-4105": (
        "Acme Packaging",
        [("AC-12", "Shipping box L", 500, 1.20), ("AC-30", "Tape 48mm", 120, 2.10)],
    ),
    "PO-4106": ("BlueRiver Logistics", [("BR-FRT", "Freight Dallas-Denver", 1, 1980.00)]),
    "PO-4107": ("Acme Packaging", [("AC-14", "Shipping box XL", 220, 1.85)]),
}
# invoice number -> (po, received ISO date, line overrides {sku: (qty, unit_price)}, is_live_test)
INVOICES = {
    "INV-2201": ("PO-4101", "2026-09-08T09:14:00Z", {}, False),
    "INV-2202": ("PO-4102", "2026-09-10T10:02:00Z", {"AC-14": (165, 1.85)}, False),  # qty over PO
    "INV-2203": ("PO-4103", "2026-09-12T08:40:00Z", {}, False),
    "INV-2204": ("PO-4104", "2026-09-15T09:30:00Z", {}, False),
    "INV-2205": (
        "PO-4105",
        "2026-09-17T11:05:00Z",
        {"AC-30": (120, 2.45)},
        False,
    ),  # price above PO
    "INV-2206": ("PO-4106", "2026-09-19T09:55:00Z", {}, False),
    "INV-2207": (
        "PO-4107",
        "2026-09-26T09:00:00Z",
        {"AC-14": (260, 1.85)},
        True,
    ),  # live test: qty over PO
}


def invoice_lines(po: str, overrides: dict) -> list[tuple]:
    return [(sku, desc, *overrides.get(sku, (qty, price))) for sku, desc, qty, price in POS[po][1]]


def expected(number: str) -> dict:
    """The contract a forged UC2 tool is gated on."""
    po, _, overrides, _ = INVOICES[number]
    vendor, po_lines = POS[po]
    lines = invoice_lines(po, overrides)
    issues = []
    for (sku, _, po_qty, po_price), (_, _, qty, price) in zip(po_lines, lines, strict=True):
        if qty != po_qty:
            issues.append({"sku": sku, "field": "qty", "po": po_qty, "invoice": qty})
        if abs(price - po_price) > 0.005:
            issues.append({"sku": sku, "field": "unit_price", "po": po_price, "invoice": price})
    total = round(sum(q * p for _, _, q, p in lines), 2)
    return {
        "invoice": number,
        "po": po,
        "vendor": vendor,
        "total": total,
        "status": "mismatch" if issues else "matched",
        "issues": issues,
    }


def write_pdf(path: Path, number: str) -> None:
    po, received, overrides, _ = INVOICES[number]
    vendor = POS[po][0]
    c = canvas.Canvas(str(path), pagesize=A4, invariant=True)  # no timestamps: same bytes every run
    c.setTitle(f"Invoice {number}")
    y = 800
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, y, vendor)
    c.setFont("Helvetica", 11)
    for text in (
        f"Invoice number: {number}",
        f"PO number: {po}",
        f"Invoice date: {received[:10]}",
        "Bill to: ACME Warehouse, Receiving Dock 3",
    ):
        y -= 22
        c.drawString(50, y, text)
    y -= 36
    c.setFont("Helvetica-Bold", 11)
    for x, head in (
        (50, "SKU"),
        (130, "Description"),
        (350, "Qty"),
        (410, "Unit price"),
        (500, "Amount"),
    ):
        c.drawString(x, y, head)
    c.setFont("Helvetica", 11)
    for sku, desc, qty, price in invoice_lines(po, overrides):
        y -= 20
        for x, value in (
            (50, sku),
            (130, desc),
            (350, str(qty)),
            (410, f"{price:.2f}"),
            (500, f"{qty * price:.2f}"),
        ):
            c.drawString(x, y, value)
    y -= 30
    c.setFont("Helvetica-Bold", 12)
    c.drawString(410, y, f"Total USD {expected(number)['total']:.2f}")
    c.save()


def main() -> None:
    (OUT / "expected").mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "po"
    ws.append(["po_number", "vendor", "sku", "description", "qty", "unit_price"])
    for po, (vendor, lines) in POS.items():
        for sku, desc, qty, price in lines:
            ws.append([po, vendor, sku, desc, qty, price])
    wb.save(OUT / "po.xlsx")

    manifest = []
    for i, (number, (po, received, _, test)) in enumerate(INVOICES.items(), 1):
        name = f"{number.lower()}.pdf"
        write_pdf(OUT / name, number)
        (OUT / "expected" / f"{number.lower()}.json").write_text(
            json.dumps(expected(number), indent=2)
        )
        # replay-gate table (gate/service.py reads expected/<input stem>_<table>.csv)
        with (OUT / "expected" / f"{number.lower()}_issues.csv").open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["sku", "field", "po", "invoice"])
            writer.writeheader()
            writer.writerows(expected(number)["issues"])
        vendor = POS[po][0]
        manifest.append(
            {
                "id": f"m{i}",
                "from": VENDORS[vendor],
                "subject": f"Invoice {number} for {po}",
                "attachment": name,
                "invoice": number,
                "received": received,
                "test": test,
            }
        )
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    mismatches = [n for n in INVOICES if expected(n)["status"] == "mismatch"]
    print(f"wrote {len(INVOICES)} invoices ({', '.join(mismatches)} mismatch) + po.xlsx to {OUT}")


if __name__ == "__main__":
    main()
