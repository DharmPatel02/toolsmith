import json

import pandas as pd

COLUMN_ALIASES = {
    "Region": ["reg", "region", "region_name"],
    "Amount": ["amt", "amount", "amount_usd", "sales"],
}


def _normalize_columns(df):
    lower = {c.strip().lower(): c for c in df.columns}
    rename = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            if a in lower:
                rename[lower[a]] = canonical
                break
    missing = [c for c in COLUMN_ALIASES if c not in rename.values()]
    if missing:
        raise ValueError(f"missing columns: {missing}; got {list(df.columns)}")
    return df.rename(columns=rename)


def run(ctx, **params):
    week = params.get("week", "")
    df = _normalize_columns(ctx.read_table("file"))
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    df = df.dropna(subset=["Region", "Amount"])
    pivot = df.pivot_table(index="Region", values="Amount", aggfunc="sum").reset_index()
    pivot = pivot.sort_values("Region").reset_index(drop=True)
    pivot["Amount"] = pivot["Amount"].round(2)
    title = f"Sales by Region - week {week}".strip()
    chart = {"type": "bar", "x": pivot["Region"].tolist(), "y": pivot["Amount"].tolist(), "title": title}
    rows = "".join(f"<tr><td>{r}</td><td>{a:,.2f}</td></tr>" for r, a in zip(chart["x"], chart["y"]))
    html = (f"<html><head><title>{title}</title></head><body><h1>{title}</h1>"
            f"<table><tr><th>Region</th><th>Amount</th></tr>{rows}</table>"
            f"<script>const chart = {json.dumps(chart)};</script></body></html>")
    ctx.write_output("dashboard.html", html)
    total = float(pivot["Amount"].sum())
    return {"summary": f"{len(pivot)} regions, total {total:,.2f}",
            "tables": {"pivot": pivot.to_dict("records")}, "chart_spec": chart}
