"""Download daily index closes (NIFTY 50, NIFTY BANK and all other NSE indices) for every
trading day already in the calendar. Resumable: days already stored are skipped.

Usage: .venv/bin/python scripts/sync_indices.py [--budget 540]
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.data.index_provider import fetch_index_day  # noqa: E402
from niftyta.data.store import PriceStore  # noqa: E402

KEEP = None  # None = store every index; set to a list of index names to limit


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=540, help="max seconds per run")
    ap.add_argument("--years", type=int, default=10)
    args = ap.parse_args()

    store = PriceStore()
    end = date.today() + timedelta(days=1)
    start = end.replace(year=end.year - args.years)
    traded = [d.date() for d in store.trading_dates(start, end)]
    done = {r[0] for r in store.conn.execute(
        "SELECT DISTINCT date FROM index_daily WHERE date >= ? AND date < ?", [start, end]).fetchall()}
    todo = [d for d in traded if d not in done]
    print(f"trading days in window {len(traded)}, already have index data {len(done)}, to fetch {len(todo)}")

    t0, fetched, missing = time.monotonic(), 0, []
    for day in todo:
        if time.monotonic() - t0 > args.budget:
            print("time budget reached; rerun to continue")
            break
        df = fetch_index_day(day)
        if df is None:
            missing.append(day.isoformat())
            continue
        store.upsert_index(df)
        fetched += 1
    print(f"fetched {fetched} days in {round(time.monotonic() - t0)}s; no index file for {len(missing)} traded days")
    if missing[:5]:
        print("  e.g.", missing[:5])
    store.close()


if __name__ == "__main__":
    main()
