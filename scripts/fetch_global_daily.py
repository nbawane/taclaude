"""Download daily bars for global indices, commodity futures and USD/INR from Yahoo Finance into DuckDB
table global_prices_daily. Re-running replaces each instrument's rows in the window.

Bars dated today or later are skipped (possibly still forming). Rows with a missing or non-positive price
are dropped; rows whose open or close falls outside high-low are kept as received and counted.
Futures are Yahoo's continuous front-month series, not adjusted for contract rolls.

Usage: .venv/bin/python scripts/fetch_global_daily.py [--years 10]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.data.store import PriceStore  # noqa: E402

INSTRUMENTS = {     # name: (Yahoo ticker, kind)
    "S&P 500": ("^GSPC", "index"), "Nasdaq Composite": ("^IXIC", "index"), "Nasdaq 100": ("^NDX", "index"),
    "Dow Jones": ("^DJI", "index"), "DAX": ("^GDAXI", "index"), "Nikkei 225": ("^N225", "index"),
    "KOSPI": ("^KS11", "index"), "Hang Seng": ("^HSI", "index"),
    "Gold futures": ("GC=F", "future"), "Silver futures": ("SI=F", "future"), "Brent crude futures": ("BZ=F", "future"),
    "USD/INR": ("INR=X", "currency"),
}
COLUMNS = ["open", "high", "low", "close", "adj_close", "volume"]


def clean(raw: pd.DataFrame, today: date) -> tuple[pd.DataFrame, dict]:
    df = raw.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close",
                             "Adj Close": "adj_close", "Volume": "volume"})[COLUMNS]
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df = df.dropna(how="all", subset=["open", "high", "low", "close"])
    df = df[df.index < pd.Timestamp(today)]
    good = (df[["open", "high", "low", "close"]] > 0).all(axis=1)
    dropped = int((~good).sum())
    df = df[good & ~df.index.duplicated(keep="last")]
    tol = 1e-6 * df["close"]
    odd = (df["high"] + tol < df[["open", "close", "low"]].max(axis=1)) | \
          (df["low"] - tol > df[["open", "close", "high"]].min(axis=1))
    return df, {"dropped": dropped, "outside_range": int(odd.sum())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", type=int, default=10)
    args = ap.parse_args()
    import yfinance as yf
    today = date.today()
    start = today - timedelta(days=365 * args.years + 10)
    got, failed = {}, []
    for name, (ticker, kind) in INSTRUMENTS.items():
        try:
            raw = yf.download(ticker, start=start.isoformat(), end=(today + timedelta(days=1)).isoformat(),
                              interval="1d", auto_adjust=False, progress=False, multi_level_index=False)
            df, notes = clean(raw, today)
            if df.empty:
                raise ValueError("no data returned")
            got[name] = (ticker, kind, df, notes)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{name} ({ticker}): {type(e).__name__}: {e}")

    store = PriceStore()
    store.conn.execute("""CREATE TABLE IF NOT EXISTS global_prices_daily (
        symbol VARCHAR NOT NULL, ticker VARCHAR NOT NULL, kind VARCHAR NOT NULL, date DATE NOT NULL,
        open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, adj_close DOUBLE, volume DOUBLE,
        PRIMARY KEY (symbol, date))""")
    for name, (ticker, kind, df, notes) in got.items():
        frame = df.rename_axis("date").reset_index()
        frame.insert(0, "symbol", name)
        frame.insert(1, "ticker", ticker)
        frame.insert(2, "kind", kind)
        store.conn.register("incoming_global", frame)
        store.conn.execute("DELETE FROM global_prices_daily WHERE symbol = ? AND date >= ?", [name, start])
        store.conn.execute("INSERT INTO global_prices_daily SELECT symbol, ticker, kind, CAST(date AS DATE), "
                           "open, high, low, close, adj_close, volume FROM incoming_global")
        store.conn.unregister("incoming_global")
        print(f"{name:20s} {ticker:7s} {len(df):5d} bars {df.index.min():%Y-%m-%d} to {df.index.max():%Y-%m-%d}"
              f" | dropped {notes['dropped']}, open/close outside high-low {notes['outside_range']}")
    store.close()
    for f in failed:
        print("FAILED", f)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
