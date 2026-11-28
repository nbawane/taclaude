"""Load NSE continuous futures daily bars (TradingView MCP responses saved as JSON) into DuckDB table
nse_futures_daily. Prices are INR, front-month, not adjusted for contract rolls.

Input: data/raw/tradingview_nsefutures/<NAME>1_1D.json (format="columns" from get_ohlcv).

Usage: .venv/bin/python scripts/load_nse_futures.py
"""
from __future__ import annotations

import sys

from load_giftnifty import ROOT, PriceStore, read_bars   # same file format; sets up the src path

SRC = ROOT / "data" / "raw" / "tradingview_nsefutures"


def main() -> None:
    store = PriceStore()
    store.conn.execute("""CREATE TABLE IF NOT EXISTS nse_futures_daily (
        symbol VARCHAR NOT NULL, date DATE NOT NULL,
        open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
        PRIMARY KEY (symbol, date))""")
    for path in sorted(SRC.glob("*_1D.json")):
        df = read_bars(path, "NSE")
        if df["date"].duplicated().any():
            sys.exit(f"{path.name}: duplicate dates, nothing loaded for this file")
        store.conn.register("incoming_fut", df)
        store.conn.execute("INSERT OR REPLACE INTO nse_futures_daily SELECT * FROM incoming_fut")
        store.conn.unregister("incoming_fut")
        print(f"{df['symbol'].iloc[0]}: {len(df)} bars, {df['date'].min()} to {df['date'].max()}")
    store.close()


if __name__ == "__main__":
    main()
