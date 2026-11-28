"""Compute monthly moves for every instrument in the database and save them for the dashboard.
Tables: monthly_moves (one row per instrument and month) and monthly_instruments (notes per instrument).
Re-run after updating prices. Nothing is downloaded.

Usage: .venv/bin/python scripts/build_monthly_moves.py [--years 10]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.analysis.monthly import monthly_moves  # noqa: E402
from niftyta.data.store import PriceStore  # noqa: E402
from niftyta.pipeline.mtf_sma_run import adjusted  # noqa: E402

ROLL = "Continuous futures contract, not adjusted for rollovers."
NOTES = {
    "NSE:NIFTY1!": ROLL, "NSEIX:NIFTY1!": ROLL + " USD priced.", "Gold futures": ROLL + " Thin data in 2016-2019.",
    "Silver futures": ROLL + " UNRELIABLE: very low volume and many flat days.", "Brent crude futures": ROLL,
    "USD/INR": "Some daily highs and lows are inconsistent: treat range figures with caution.",
}
# GIFT Bank Nifty is left out: it has almost no traded volume.
SOURCES = (
    ("Futures", "SELECT symbol, date, open, high, low, close FROM nse_futures_daily"),
    ("Futures", "SELECT symbol, date, open, high, low, close FROM giftnifty_futures_daily "
                "WHERE symbol = 'NSEIX:NIFTY1!'"),
    ("Indian indices", "SELECT index_name AS symbol, date, open, high, low, close FROM index_daily "
                       "WHERE index_name IN ('Nifty 50', 'Nifty Bank', 'Nifty 500')"),
    ("Global", "SELECT symbol, kind, date, open, high, low, close FROM global_prices_daily"),
    ("Stocks", "SELECT * FROM yfinance_prices_daily"),
)
KINDS = {"index": "Global indices", "future": "Commodities", "currency": "Currency"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=10)
    args = ap.parse_args()
    today = pd.Timestamp.today().normalize()
    since = (today - pd.DateOffset(years=args.years)).to_period("M") - 1    # one extra month for the first move
    store = PriceStore()
    moves, info = [], []
    for group, sql in SOURCES:
        data = store.conn.execute(sql + (" ORDER BY symbol, date")).df()
        data["date"] = pd.to_datetime(data["date"])
        for symbol, d in data.groupby("symbol"):
            d = d.set_index("date").dropna(subset=["open", "high", "low", "close"])
            if group == "Stocks":
                d = adjusted(d.dropna(subset=["adj_close"]))
            g = KINDS[d["kind"].iloc[0]] if group == "Global" else group
            d = d[d.index >= since.start_time]
            m = monthly_moves(d, today)
            if m.empty:
                continue
            moves.append(m.assign(symbol=symbol))
            done = m[m["complete"]]
            info.append({"symbol": symbol, "grp": g, "months": len(done),
                         "first_month": f"{done.year.iloc[0]}-{done.month.iloc[0]:02d}" if len(done) else None,
                         "last_month": f"{done.year.iloc[-1]}-{done.month.iloc[-1]:02d}" if len(done) else None,
                         "data_to": d.index.max().date(), "note": NOTES.get(symbol, "")})
    moves, info = pd.concat(moves, ignore_index=True), pd.DataFrame(info)
    store.conn.register("m", moves)
    store.conn.register("i", info)
    store.conn.execute("CREATE OR REPLACE TABLE monthly_moves AS SELECT symbol, CAST(year AS INTEGER) AS year, "
                       "CAST(month AS INTEGER) AS month, open, high, low, close, prev_close, return_pct, up_pct, "
                       "down_pct, range_pct, CAST(days AS INTEGER) AS days, complete FROM m")
    store.conn.execute("CREATE OR REPLACE TABLE monthly_instruments AS SELECT * FROM i")
    store.close()
    print(f"saved {len(moves):,} monthly rows for {len(info)} instruments")
    print(info.groupby("grp").agg(instruments=("symbol", "size"), median_months=("months", "median")).to_string())


if __name__ == "__main__":
    main()
