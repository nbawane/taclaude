"""Download/refresh NSE daily bhavcopy into data/niftyta.db.

Usage (from project root):
    .venv/bin/python scripts/sync_daily.py                # last 10 years, up to 9 minutes per run
    .venv/bin/python scripts/sync_daily.py --years 10 --budget 540 --symbol RELIANCE

Safe to rerun: days already stored are skipped, so a run that stopped early resumes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.data.service import get_daily  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--budget", type=float, default=540, help="max seconds of downloading this run")
    ap.add_argument("--symbol", default="RELIANCE", help="symbol to report on after sync")
    args = ap.parse_args()

    df, gaps, rep = get_daily(args.symbol, years=args.years, budget_seconds=args.budget)
    print(f"sync: {rep.summary()}")
    if df.empty:
        print(f"{args.symbol}: no rows yet (run again to continue the download)")
    else:
        print(f"{args.symbol}: {len(df)} rows, {df.index.min():%Y-%m-%d} -> {df.index.max():%Y-%m-%d}")
        print(f"{args.symbol} sessions without a bar inside its history: {len(gaps)}")


if __name__ == "__main__":
    main()
