"""Backtest the SMA20 cross strategy on every symbol in yfinance_prices_daily.
Rule: buy at the next open after the close crosses above SMA(20); sell at the next open after it crosses below.
Prices are dividend- and split-adjusted. Costs and slippage from config/costs.yaml.
Each symbol is a separate 100,000 INR account. Compared with buy and hold over the same dates.

Usage: .venv/bin/python scripts/sma20.py [--period 20] [--min-bars 250]
Output: reports/sma20_by_symbol.csv and a summary on screen.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.backtest.engine import run_backtest  # noqa: E402
from niftyta.backtest.metrics import performance  # noqa: E402
from niftyta.backtest.runner import IN_SAMPLE_FRACTION  # noqa: E402
from niftyta.backtest.strategies import sma_cross_signals  # noqa: E402
from niftyta.data.store import PriceStore  # noqa: E402


def main() -> None:
    cfg = yaml.safe_load(open(ROOT / "config" / "strategies.yaml"))["sma_cross"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=int, default=cfg["period"])
    ap.add_argument("--min-bars", type=int, default=250)
    args = ap.parse_args()

    store = PriceStore()
    data = store.conn.execute("SELECT * FROM yfinance_prices_daily ORDER BY symbol, date").df()
    store.close()

    rows, skipped = [], 0
    for symbol, df in data.groupby("symbol"):
        df = df.set_index("date").dropna(subset=["open", "close", "adj_close"])
        if len(df) < args.min_bars:
            skipped += 1
            continue
        factor = df["adj_close"] / df["close"]
        df = df.assign(open=df["open"] * factor, close=df["adj_close"])
        entry, exit_ = sma_cross_signals(df["close"], args.period)   # computed on full history
        split = int(len(df) * IN_SAMPLE_FRACTION)
        for period, (a, b) in {"full": (0, len(df)), "in_sample": (0, split), "out_of_sample": (split, len(df))}.items():
            sub = df.iloc[a:b]
            res = run_backtest(sub, entry[a:b], exit_[a:b])
            m = performance(res.equity, res.trades, res.exposure)
            hold = np.zeros(len(sub), bool)
            hold[0] = True
            bh_res = run_backtest(sub, hold, np.zeros(len(sub), bool))
            bh = performance(bh_res.equity, bh_res.trades, bh_res.exposure)
            rows.append({"symbol": symbol, "period": period, "from": sub.index[0].date(), "to": sub.index[-1].date(),
                         **m, "bh_total_return": bh["total_return"], "bh_cagr": bh["cagr"],
                         "bh_max_drawdown": bh["max_drawdown"]})

    import pandas as pd
    out = pd.DataFrame(rows)
    path = ROOT / "reports" / f"sma{args.period}_by_symbol.csv"
    path.parent.mkdir(exist_ok=True)
    out.to_csv(path, index=False)
    print(f"SMA{args.period}: {out['symbol'].nunique()} symbols tested, {skipped} skipped (< {args.min_bars} bars)")
    for period, g in out.groupby("period", sort=False):
        print(f"\n{period}: medians across symbols")
        print(f"  CAGR            strategy {g['cagr'].median():7.1%}   buy&hold {g['bh_cagr'].median():7.1%}")
        print(f"  max drawdown    strategy {g['max_drawdown'].median():7.1%}   buy&hold {g['bh_max_drawdown'].median():7.1%}")
        print(f"  trades {g['trades'].median():.0f} | win rate {g['win_rate'].median():.1%} | profit factor {g['profit_factor'].median():.2f}"
              f" | time in market {g['exposure'].median():.0%}")
        print(f"  beats buy&hold on CAGR: {(g['cagr'] > g['bh_cagr']).mean():.0%} of symbols"
              f" | profitable: {(g['total_return'] > 0).mean():.0%}"
              f" | smaller drawdown: {(g['max_drawdown'] > g['bh_max_drawdown']).mean():.0%}")
    print(f"\nper symbol: {path}")


if __name__ == "__main__":
    main()
