"""UC1 reference: Monday sales workbook -> pivot by Region + bar chart spec.

    python reference.py           # recompute expected/ from the week*.xlsx files
    python reference.py --build   # also regenerate the week*.xlsx files (deterministic data)

Shape (see docs/status/P2_split.md, "UC1 artifacts"):
- week1/2/4.xlsx columns: date, reg, product, amt
- week3.xlsx is renamed:  date, region_name, product, amount   (drift the tool must absorb)
- messy on purpose: amounts stored as text, missing amounts, a row with no region, an empty row
- steps: rename -> dropna -> cast float -> pivot sum by Region (the UC1 pattern signature)
"""
from __future__ import annotations

import csv
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent
EXPECTED = ROOT / "expected"
MONDAYS = {1: date(2026, 9, 7), 2: date(2026, 9, 14), 3: date(2026, 9, 21), 4: date(2026, 9, 28)}
REGIONS = ["Central", "East", "North", "South", "West"]
PRODUCTS = ["Hardware", "Software", "Services"]
HEADERS = {w: ["date", "reg", "product", "amt"] for w in MONDAYS}
HEADERS[3] = ["date", "region_name", "product", "amount"]
RENAME = {"reg": "Region", "region_name": "Region", "amt": "Amount", "amount": "Amount"}


def rows_for(week: int) -> list[list]:
    rng = random.Random(1000 + week)
    day = MONDAYS[week] - timedelta(days=7)
    rows: list[list] = []
    for i in range(36):
        amt: object = round(rng.uniform(150, 2500), 2)
        if i % 7 == 3:
            amt = f"{amt:.2f}"           # number stored as text
        if i % 11 == 5:
            amt = None                   # missing amount
        region = REGIONS[(i * 3 + week) % len(REGIONS)] if i != 17 else None  # one row without region
        rows.append([(day + timedelta(days=i % 5)).isoformat(), region, PRODUCTS[i % 3], amt])
    rows.insert(20, [None, None, None, None])  # empty row
    return rows


def build_workbooks() -> None:
    for week in MONDAYS:
        wb = Workbook()
        ws = wb.active
        ws.title = "Sales"
        ws.append(HEADERS[week])
        for row in rows_for(week):
            ws.append(row)
        wb.save(ROOT / f"week{week}.xlsx")


def pivot(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path).rename(columns=RENAME)
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    df = df.dropna(subset=["Region", "Amount"])
    out = df.pivot_table(index="Region", values="Amount", aggfunc="sum").reset_index()
    out = out.sort_values("Region").reset_index(drop=True)
    out["Amount"] = out["Amount"].round(2)
    return out


def chart(p: pd.DataFrame, week: int) -> dict:
    return {"type": "bar", "x": p["Region"].tolist(), "y": [float(v) for v in p["Amount"]],
            "title": f"Sales by Region - week {week}"}


def write_expected() -> None:
    EXPECTED.mkdir(parents=True, exist_ok=True)
    for week in sorted(MONDAYS):
        p = pivot(ROOT / f"week{week}.xlsx")
        with (EXPECTED / f"week{week}_pivot.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Region", "Amount"])
            w.writerows([r, f"{a:.2f}"] for r, a in zip(p["Region"], p["Amount"], strict=True))
        (EXPECTED / f"week{week}_chart.json").write_text(
            json.dumps(chart(p, week), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if "--build" in sys.argv:
        build_workbooks()
    write_expected()
