"""Backtest the three strategies plus buy-and-hold on a stock, at a chosen timeframe.
Prices are RAW (unadjusted) until corporate-action adjustment is added.

Usage: .venv/bin/python scripts/backtest.py RELIANCE [--timeframe 1D|1W|1M]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from niftyta.backtest.metrics import PERIODS_PER_YEAR  # noqa: E402
from niftyta.backtest.runner import run_all, summary_frame  # noqa: E402
from niftyta.data.store import PriceStore  # noqa: E402
from niftyta.data.timeframes import resample_ohlcv  # noqa: E402
from niftyta.indicators.core import load_params  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="RELIANCE")
    ap.add_argument("--timeframe", default="1D", choices=["1D", "1W", "1M"])
    args = ap.parse_args()
    symbol = args.symbol.upper()

    store = PriceStore()
    end = date.today() + timedelta(days=1)
    daily = store.load(symbol, end.replace(year=end.year - 10), end)
    store.close()
    if daily.empty:
        sys.exit(f"No stored data for {symbol}. Run scripts/sync_daily.py first.")

    bars = resample_ohlcv(daily, args.timeframe)
    bars = bars[~bars["partial"]]  # never trade on a bar that is still forming
    strat = yaml.safe_load(open(ROOT / "config" / "strategies.yaml"))
    results = run_all(bars, load_params(), strat, PERIODS_PER_YEAR[args.timeframe])
    summary = summary_frame(results)

    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    tag = f"{symbol}_{args.timeframe}"
    summary.to_csv(out_dir / f"{tag}_backtest_summary.csv", index=False, float_format="%.4f")
    trades = [r.result.trades.assign(strategy=r.strategy) for r in results
              if r.period == "full" and len(r.result.trades)]
    if trades:
        pd.concat(trades).to_csv(out_dir / f"{tag}_backtest_trades.csv", index=False, float_format="%.4f")

    show = summary[["period", "strategy", "total_return", "cagr", "max_drawdown", "sharpe",
                    "trades", "win_rate", "profit_factor", "exposure"]]
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(f"{symbol} {args.timeframe}: {len(bars)} bars, {bars.index.min():%Y-%m-%d} -> {bars.index.max():%Y-%m-%d}")
        print(show.round(3).to_string(index=False))
    print(f"\nsummary: {out_dir / (tag + '_backtest_summary.csv')}")


if __name__ == "__main__":
    main()
