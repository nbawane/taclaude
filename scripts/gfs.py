"""Run the Bullish GFS + RSI divergence strategy on a stock.
Usage: .venv/bin/python scripts/gfs.py RELIANCE [--years 10]
Parameters: config/strategies.yaml (gfs). Rules: docs/strategies/gfs.md.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from niftyta.data.store import PriceStore  # noqa: E402
from niftyta.pipeline.gfs_run import run_gfs  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="RELIANCE")
    ap.add_argument("--years", type=int, default=10)
    args = ap.parse_args()
    sym = args.symbol.upper()
    store = PriceStore()
    end = date.today() + timedelta(days=1)
    daily = store.load(sym, end.replace(year=end.year - args.years), end)
    store.close()
    if daily.empty:
        sys.exit(f"No stored data for {sym}. Run scripts/sync_daily.py first.")
    summary, trades = run_gfs(daily, sym)
    if summary.empty:
        sys.exit("no results")
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    summary.to_csv(out / f"{sym}_GFS_summary.csv", index=False, float_format="%.4f")
    if trades:
        pd.concat(trades.values()).to_csv(out / f"{sym}_GFS_trades.csv", index=False, float_format="%.4f")
    show = summary[["variant", "exit", "period", "trades", "win_rate", "profit_factor", "max_drawdown",
                    "expectancy_R", "total_return", "exposure"]]
    with pd.option_context("display.width", 220, "display.max_columns", 20):
        print(f"{sym} GFS (Grandfather M, Father W, Son D), {daily.index.min():%Y-%m-%d} -> {daily.index.max():%Y-%m-%d}")
        print(show.round(3).to_string(index=False))
    from niftyta.data.corporate_actions import load_actions
    if load_actions() is None:
        print("\nWARNING: prices are NOT adjusted for corporate actions (data/reference/corporate_actions.csv missing). Results are provisional.")
    print(f"\nsummary: {out / (sym + '_GFS_summary.csv')}")


if __name__ == "__main__":
    main()
