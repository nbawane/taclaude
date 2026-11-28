"""Load GIFT Nifty / Bank Nifty continuous futures daily bars (TradingView MCP responses saved as JSON)
into DuckDB table giftnifty_futures_daily, kept apart from NSE data.

Input: data/raw/tradingview_giftnifty/<NAME>1_1D.json (format="columns" from get_ohlcv).
The date is the IST date of the bar's open. Bars dated today or later are skipped (still forming).

Usage: .venv/bin/python scripts/load_giftnifty.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.data.store import PriceStore  # noqa: E402

SRC = ROOT / "data" / "raw" / "tradingview_giftnifty"


def read_bars(path: Path, exchange: str = "NSEIX") -> pd.DataFrame:
    b = pd.DataFrame(json.loads(path.read_text())["bars"])
    ist = pd.to_datetime(b["t"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    df = pd.DataFrame({"symbol": exchange + ":" + path.name.replace("_1D.json", "!"), "date": ist.dt.date,
                       "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"], "volume": b["v"]})
    return df[df["date"] < pd.Timestamp.now("Asia/Kolkata").date()]


def main() -> None:
    store = PriceStore()
    store.conn.execute("""CREATE TABLE IF NOT EXISTS giftnifty_futures_daily (
        symbol VARCHAR NOT NULL, date DATE NOT NULL,
        open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
        PRIMARY KEY (symbol, date))""")   # continuous front-month, not roll-adjusted
    for path in sorted(SRC.glob("*_1D.json")):
        df = read_bars(path)
        if df["date"].duplicated().any():
            sys.exit(f"{path.name}: duplicate dates, nothing loaded for this file")
        store.conn.register("incoming_gift", df)
        store.conn.execute("INSERT OR REPLACE INTO giftnifty_futures_daily SELECT * FROM incoming_gift")
        store.conn.unregister("incoming_gift")
        print(f"{df['symbol'].iloc[0]}: {len(df)} bars, {df['date'].min()} to {df['date'].max()}")
    store.close()


if __name__ == "__main__":
    main()
