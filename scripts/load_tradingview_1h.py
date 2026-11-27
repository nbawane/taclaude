"""Load TradingView hourly bars into DuckDB table tradingview_prices_1h (separate from NSE prices_daily).
Input: CSV or JSON files in a directory, one per symbol (name = SYMBOL.csv / SYMBOL.json) or with a
`symbol` column. Columns: t (unix sec UTC) or ts, and o/h/l/c/v or open/high/low/close/volume.
Usage: .venv/bin/python scripts/load_tradingview_1h.py DIR
       .venv/bin/python scripts/load_tradingview_1h.py --status
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.data.store import PriceStore  # noqa: E402

RENAME = {"t": "ts", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}


def read_file(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_json(path)
    df = df.rename(columns=RENAME)
    if pd.api.types.is_numeric_dtype(df["ts"]):
        df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    else:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["ts"] = df["ts"].dt.tz_localize(None)
    if "symbol" not in df:
        df["symbol"] = path.stem.upper().removeprefix("NSE_")
    df["symbol"] = df["symbol"].str.replace("NSE:", "", regex=False).str.upper()
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    store = PriceStore()
    if args.status:
        print(store.conn.execute("SELECT count(DISTINCT symbol) symbols, count(*) bars, min(ts) first, max(ts) last "
                                 "FROM tradingview_prices_1h").df().to_string(index=False))
    else:
        files = sorted(p for p in Path(args.dir).iterdir() if p.suffix in (".csv", ".json"))
        total = sum(store.upsert_tv_1h(read_file(f)) for f in files)
        print(f"loaded {total} bars from {len(files)} files")
    store.close()


if __name__ == "__main__":
    main()
