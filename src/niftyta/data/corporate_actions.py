"""Backward price adjustment for splits, bonuses and similar events.

Input file: data/reference/corporate_actions.csv with columns
    symbol, ex_date (YYYY-MM-DD), factor
where factor is the price multiplier for bars BEFORE ex_date.
Examples: 1:1 bonus -> 0.5 ; face-value split 10 -> 1 (1:10) -> 0.1 ; no adjustment -> 1.0
Volumes before ex_date are divided by the factor so value traded stays consistent.
If the file is missing, prices stay raw and the report says so.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FILE = PROJECT_ROOT / "data" / "reference" / "corporate_actions.csv"
PRICE_COLS = ["open", "high", "low", "close", "adj_close"]


def load_actions(path: Path = DEFAULT_FILE) -> pd.DataFrame | None:
    if not Path(path).exists():
        return None
    df = pd.read_csv(path, parse_dates=["ex_date"])
    df["symbol"] = df["symbol"].str.strip().str.upper()
    if (df["factor"] <= 0).any():
        raise ValueError("corporate action factor must be positive")
    return df


def adjust_bars(bars: pd.DataFrame, actions: pd.DataFrame | None, symbol: str) -> tuple[pd.DataFrame, int]:
    """Return (adjusted copy, number of actions applied). bars indexed by date."""
    out = bars.copy()
    if actions is None or actions.empty:
        return out, 0
    mine = actions[actions["symbol"] == symbol.upper()].sort_values("ex_date")
    applied = 0
    for _, a in mine.iterrows():
        before = out.index < a["ex_date"]
        if not before.any():
            continue
        for c in PRICE_COLS:
            if c in out:
                out.loc[before, c] = out.loc[before, c] * a["factor"]
        if "volume" in out:
            out.loc[before, "volume"] = out.loc[before, "volume"] / a["factor"]
        applied += 1
    return out, applied
