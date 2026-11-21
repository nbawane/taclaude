"""Phase 4 charts and tables for one stock and timeframe.
Usage: .venv/bin/python scripts/performance_report.py RELIANCE --timeframe 1D
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from niftyta.backtest.runner import BUY_AND_HOLD  # noqa: E402
from niftyta.pipeline.run import analyse  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="RELIANCE")
    ap.add_argument("--timeframe", default="1D", choices=["1D", "1W", "1M"])
    args = ap.parse_args()
    a = analyse(args.symbol, args.timeframe)
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    tag = f"{a.symbol}_{a.timeframe}"
    a.summary.to_csv(reports / f"{tag}_summary.csv", index=False, float_format="%.4f")

    full = [r for r in a.results if r.period == "full"]
    fig, (ax_eq, ax_dd) = plt.subplots(2, 1, figsize=(12, 9), sharex=True,
                                       gridspec_kw={"height_ratios": [3, 1.5]})
    for r in full:
        eq = r.result.equity / r.result.equity.iloc[0] * 100
        dd = (eq / eq.cummax() - 1) * 100
        lw = 2 if r.strategy == BUY_AND_HOLD else 1
        ax_eq.plot(eq.index, eq, lw=lw, label=f"{r.strategy} ({r.metrics['total_return']:+.0%})")
        ax_dd.plot(dd.index, dd, lw=lw, label=r.strategy)
    banner = ("adjusted for corporate actions" if a.adjusted and a.adjustments_applied
              else "RAW unadjusted prices: bonus/split drops appear as losses")
    ax_eq.set_title(f"{a.symbol} {a.timeframe}: equity curves (start = 100), costs included\n{banner}", fontsize=10)
    ax_eq.set_ylabel("Equity (start = 100)")
    ax_eq.set_yscale("log")
    ax_eq.legend(fontsize=8, loc="upper left")
    ax_eq.grid(alpha=0.3)
    ax_dd.set_ylabel("Drawdown %")
    ax_dd.set_xlabel("Date")
    ax_dd.grid(alpha=0.3)
    if len(a.bars):
        split = a.bars.index[int(len(a.bars) * 0.7)]
        for ax in (ax_eq, ax_dd):
            ax.axvline(split, color="black", ls=":", lw=1)
        ax_eq.text(split, ax_eq.get_ylim()[1], " out-of-sample →", fontsize=8, va="top")
    fig.tight_layout()
    png = reports / f"{tag}_performance.png"
    fig.savefig(png, dpi=120)

    show = a.summary[["period", "strategy", "total_return", "cagr", "max_drawdown", "sharpe",
                      "trades", "win_rate", "profit_factor", "exposure"]]
    import pandas as pd
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(f"{a.symbol} {a.timeframe}: {len(a.bars)} closed bars, "
              f"{a.bars.index.min():%Y-%m-%d} -> {a.bars.index.max():%Y-%m-%d}, "
              f"adjustments applied: {a.adjustments_applied}")
        print(show.round(3).to_string(index=False))
    print(f"\nchart: {png}\ntable: {reports / (tag + '_summary.csv')}")


if __name__ == "__main__":
    main()
