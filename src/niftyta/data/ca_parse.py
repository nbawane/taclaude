"""Parse NSE's corporate-actions CSV export (CF-CA-equities-<SYMBOL>-....csv) into price factors.

Only events whose price effect is fully defined by the text are converted:
  Bonus a:b                      -> a new shares for every b held   -> factor b / (a + b)
  Face value split, From Rs X To Rs Y                               -> factor Y / X
Everything else is kept in the log but NOT applied, because the file alone cannot give the price effect:
  Dividend    needs the amount against that day's price (a total-return adjustment, not a price one)
  Rights      needs the issue price and ratio against the market price
  Demerger    needs the ratio and the value of the spun-off shares
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

EXPORT_COLUMNS = {"SYMBOL": "symbol", "PURPOSE": "purpose", "EX-DATE": "ex_date"}


def classify(purpose: str) -> tuple[str, float | None, str]:
    """(kind, factor or None, note) for one NSE purpose string."""
    p = " ".join(purpose.split())
    low = p.lower()
    m = re.search(r"bonus\s+(\d+)\s*:\s*(\d+)", low)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return "bonus", b / (a + b), f"{a} new for every {b} held"
    if "split" in low or "sub-division" in low or "sub division" in low:
        m = re.search(r"from\s+rs\.?\s*([\d.]+).*?to\s+rs\.?\s*([\d.]+)", low)
        if m:
            old, new = float(m.group(1)), float(m.group(2))
            return "split", new / old, f"face value {old:g} -> {new:g}"
        return "split", None, "split text not understood; review by hand"
    if "demerger" in low or "scheme of arrangement" in low or "spin" in low:
        return "demerger", None, "price effect not in the file; not applied"
    if "rights" in low:
        return "rights", None, "needs issue price and ratio; not applied"
    if "dividend" in low:
        return "dividend", None, "not a price adjustment; not applied"
    return "other", None, "not applied"


def parse_export(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    raw.columns = raw.columns.str.strip()
    df = raw.rename(columns=EXPORT_COLUMNS)[["symbol", "ex_date", "purpose"]].copy()
    df["symbol"] = df["symbol"].str.strip().str.upper()
    df["ex_date"] = pd.to_datetime(df["ex_date"].str.strip(), format="%d-%b-%Y")
    parsed = df["purpose"].astype(str).map(classify)
    df["kind"] = [k for k, _, _ in parsed]
    df["factor"] = [f for _, f, _ in parsed]
    df["note"] = [n for _, _, n in parsed]
    df["purpose"] = df["purpose"].astype(str).str.split().str.join(" ")
    return df.sort_values(["symbol", "ex_date"]).reset_index(drop=True)
