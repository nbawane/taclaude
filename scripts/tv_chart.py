"""TradingView-style charts for one stock, in one window.

Default: three panels side by side, daily | weekly | monthly. Each panel has candlesticks,
Bollinger Bands (20, 2σ), SMA 20 and SMA 50 on top, and RSI(14) in a pane below.

Reads stored daily bars from data/niftyta.duckdb (read-only), builds weekly/monthly bars with the
project's resampler, and takes all indicator periods from config/indicators.yaml.

Usage:
    .venv/bin/python scripts/tv_chart.py RELIANCE                # daily | weekly | monthly
    .venv/bin/python scripts/tv_chart.py RELIANCE --tf 1D        # one timeframe, full window
    .venv/bin/python scripts/tv_chart.py RELIANCE --years 10
    .venv/bin/python scripts/tv_chart.py RELIANCE --dry-run      # print data summary, no window
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

from niftyta.data.provider import COLUMNS  # noqa: E402
from niftyta.data.store import DEFAULT_DB  # noqa: E402
from niftyta.data.timeframes import resample_ohlcv  # noqa: E402
from niftyta.indicators.core import compute_indicators, load_params  # noqa: E402

TIMEFRAMES = {"1D": "Daily", "1W": "Weekly", "1M": "Monthly"}


def load_daily(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Read-only query, so the chart never takes the write lock on the database."""
    con = duckdb.connect(str(DEFAULT_DB), read_only=True)
    try:
        df = con.execute(
            f"SELECT date, {', '.join(COLUMNS)} FROM prices_daily "
            "WHERE symbol = ? AND date >= ? AND date < ? ORDER BY date",
            [symbol, start, end]).df()
    finally:
        con.close()
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def build_frame(symbol: str, tf: str, years: int) -> pd.DataFrame:
    """Bars for one timeframe with indicators. Indicators use this timeframe's own bars."""
    end = date.today() + timedelta(days=1)
    start = end.replace(year=end.year - years)
    daily = load_daily(symbol, start, end)
    if daily.empty:
        sys.exit(f"No stored data for {symbol}. Run scripts/sync_daily.py first.")
    bars = resample_ohlcv(daily, tf)
    return bars.join(compute_indicators(bars, load_params()))


def to_chart_frame(df: pd.DataFrame, cols: list[str], rename: dict | None = None) -> pd.DataFrame:
    """lightweight-charts needs a 'time' column; warm-up NaNs are dropped so lines start where data exists."""
    out = df[cols].dropna().reset_index().rename(columns={"date": "time"})
    out["time"] = out["time"].astype("datetime64[ns]")   # the library assumes nanoseconds
    return out.rename(columns=rename or {})


def fill_panel(pane, full: pd.DataFrame, tf: str, p: dict, rsi_sync: str | bool):
    """Candles, bands, MAs on `pane`, and an RSI pane underneath it."""
    rsi_col = f"rsi_{p['rsi']['period']}"
    sma_s, sma_l = f"sma_{p['sma_short']['period']}", f"sma_{p['sma_long']['period']}"
    b = p["bbands"]
    bb_u, bb_m, bb_l = (f"bb_{k}_{b['period']}_{b['std']}" for k in ("upper", "middle", "lower"))

    pane.candle_style(up_color="#26a69a", down_color="#ef5350", border_up_color="#26a69a",
                      border_down_color="#ef5350", wick_up_color="#26a69a", wick_down_color="#ef5350")
    pane.set(to_chart_frame(full, ["open", "high", "low", "close"]))

    for col, label, color, style in [
        (bb_u, "BB upper", "rgba(120,123,134,0.8)", "dotted"),
        (bb_m, "BB mid", "rgba(120,123,134,0.6)", "solid"),
        (bb_l, "BB lower", "rgba(120,123,134,0.8)", "dotted"),
        (sma_s, f"SMA {p['sma_short']['period']}", "#f5a623", "solid"),
        (sma_l, f"SMA {p['sma_long']['period']}", "#2962ff", "solid"),
    ]:
        line = pane.create_line(name=label, color=color, style=style, width=1,
                                price_label=False, price_line=False)
        line.set(to_chart_frame(full, [col], {col: label}))

    rsi_name = f"RSI {p['rsi']['period']}"
    rsi_pane = pane.create_subchart(position="bottom", width=1, height=0.3, sync=rsi_sync)
    rsi_line = rsi_pane.create_line(name=rsi_name, color="#9c27b0", width=1,
                                    price_label=True, price_line=False)
    rsi_line.set(to_chart_frame(full, [rsi_col], {rsi_col: rsi_name}))
    rsi_pane.horizontal_line(70, color="rgba(239,83,80,0.7)", style="dashed", width=1)
    rsi_pane.horizontal_line(30, color="rgba(38,166,154,0.7)", style="dashed", width=1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--tf", choices=list(TIMEFRAMES), help="show just this timeframe, full window")
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true", help="print data summary, do not open a window")
    args = ap.parse_args()
    symbol = args.symbol.upper()
    p = load_params()
    tfs = [args.tf] if args.tf else ["1D", "1W", "1M"]

    frames = {tf: build_frame(symbol, tf, args.years) for tf in tfs}
    for tf, full in frames.items():
        print(f"{symbol} {TIMEFRAMES[tf]}: {len(full)} bars, "
              f"{full.index.min():%Y-%m-%d} -> {full.index.max():%Y-%m-%d}")
    if args.dry_run:
        return

    from lightweight_charts import Chart  # imported here so --dry-run works without a display

    n = len(tfs)
    width = 1 / n
    # Panels sit side by side in one window; the first one is the window's main chart.
    main_chart = Chart(title=f"{symbol}", inner_width=width, inner_height=1,
                       width=1600 if n > 1 else 1100, height=820)
    main_chart.legend(visible=True, font_size=12)
    panels = [main_chart]
    for _ in range(n - 1):
        panels.append(panels[-1].create_subchart(position="right", width=width, height=1,
                                                 sync=False))

    for tf, pane in zip(tfs, panels):
        pane.topbar.textbox("title", f"{symbol} · {TIMEFRAMES[tf]}")
        fill_panel(pane, frames[tf], tf, p, rsi_sync=True)  # RSI pane follows its own price pane

    main_chart.show(block=True)


if __name__ == "__main__":
    main()
