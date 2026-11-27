"""List likely splits/bonuses from stored prices, as CANDIDATES for review.

Usage: .venv/bin/python scripts/detect_corporate_actions.py            # Nifty 50 + Bank Nifty
       .venv/bin/python scripts/detect_corporate_actions.py --all      # every stored stock
Writes data/reference/corporate_actions_candidates.csv. To apply, copy the confirmed rows
(symbol, ex_date, factor) into data/reference/corporate_actions.csv.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from niftyta.data.ca_detect import find_candidates  # noqa: E402
from niftyta.data.store import PriceStore  # noqa: E402
from niftyta.universe import universe  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="scan every stored stock, not just the index universe")
    args = ap.parse_args()
    store = PriceStore()
    if args.all:
        df = store.conn.execute("SELECT symbol, date, close, volume FROM prices_daily").df()
    else:
        syms = universe()
        df = store.conn.execute("SELECT symbol, date, close, volume FROM prices_daily "
                                "WHERE symbol IN (SELECT UNNEST(?))", [syms]).df()
    store.close()
    cand = find_candidates(df)
    out = ROOT / "data" / "reference" / "corporate_actions_candidates.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cand.sort_values(["symbol", "ex_date"]).to_csv(out, index=False)
    print(f"scanned {df.symbol.nunique()} stocks; {len(cand)} candidate event(s)")
    if len(cand):
        with pd.option_context("display.width", 200, "display.max_columns", 20, "display.max_rows", 200):
            print(cand.sort_values(["symbol", "ex_date"])[["symbol", "ex_date", "prev_close", "close", "ratio",
                  "suggested_factor", "pattern", "volume_vs_20d_avg", "confidence"]].to_string(index=False))
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
