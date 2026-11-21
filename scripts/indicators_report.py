"""Compute configured indicators for a stock from data/niftyta.db.
Writes data/derived/<SYMBOL>_indicators.csv and reports/<SYMBOL>_indicators.png.

Usage: .venv/bin/python scripts/indicators_report.py RELIANCE
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from niftyta.data.store import PriceStore  # noqa: E402
from niftyta.indicators.core import compute_indicators, load_params  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    args = ap.parse_args()
    symbol = args.symbol.upper()

    store = PriceStore()
    end = date.today() + timedelta(days=1)
    prices = store.load(symbol, end.replace(year=end.year - 5), end)
    store.close()
    if prices.empty:
        sys.exit(f"No stored data for {symbol}. Run scripts/sync_daily.py first.")

    params = load_params()
    ind = compute_indicators(prices, params)
    out = prices.join(ind)

    derived = ROOT / "data" / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    csv_path = derived / f"{symbol}_indicators.csv"
    out.to_csv(csv_path, float_format="%.4f")

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    png_path = reports / f"{symbol}_indicators.png"
    fig, (ax, ax_rsi) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                     gridspec_kw={"height_ratios": [3, 1]})
    ax.plot(out.index, out["close"], color="black", lw=1, label="Close")
    ax.plot(out.index, out["ema_9"], lw=1, label="EMA 9")
    ax.plot(out.index, out["ema_21"], lw=1, label="EMA 21")
    ax.plot(out.index, out["sma_20"], lw=1, ls="--", label="SMA 20")
    ax.plot(out.index, out["sma_50"], lw=1, ls="--", label="SMA 50")
    ax.plot(out.index, out["bb_upper_20_2"], color="grey", lw=0.7)
    ax.plot(out.index, out["bb_lower_20_2"], color="grey", lw=0.7, label="Bollinger 20, 2σ")
    ax.fill_between(out.index, out["bb_lower_20_2"], out["bb_upper_20_2"], color="grey", alpha=0.08)
    ax.set_title(f"{symbol} daily close with indicators (raw, unadjusted prices)")
    ax.legend(loc="upper left", fontsize=8, ncol=3)
    ax.grid(alpha=0.3)
    ax_rsi.plot(out.index, out["rsi_14"], color="purple", lw=1, label="RSI 14")
    ax_rsi.axhline(70, color="red", lw=0.7, ls=":")
    ax_rsi.axhline(30, color="green", lw=0.7, ls=":")
    ax_rsi.set_ylim(0, 100)
    ax_rsi.legend(loc="upper left", fontsize=8)
    ax_rsi.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)

    print(f"rows {len(out)}, {out.index.min():%Y-%m-%d} -> {out.index.max():%Y-%m-%d}")
    print(f"csv: {csv_path}")
    print(f"chart: {png_path}")


if __name__ == "__main__":
    main()
