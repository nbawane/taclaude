"""Run GFS (Grandfather = month, Father = week, Son = day) on every stock in yfinance_prices_daily,
both trigger modes and both exits. Each stock is its own all-in account.

Usage: .venv/bin/python scripts/gfs_all.py
Output: reports/gfs/by_symbol.csv and trades.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.backtest.portfolio import PortfolioConfig  # noqa: E402
from niftyta.data.store import DEFAULT_DB  # noqa: E402
from niftyta.pipeline import tester  # noqa: E402
from niftyta.strategies import all_strategies  # noqa: E402

MIN_BARS = 250


def main() -> None:
    gfs = all_strategies()["gfs"]
    with duckdb.connect(str(DEFAULT_DB), read_only=True) as conn:
        px = conn.execute("SELECT * FROM yfinance_prices_daily ORDER BY symbol, date").df()
    px["date"] = pd.to_datetime(px["date"])
    cfg = PortfolioConfig(max_positions=1, max_position_pct=1.0)
    rows, trades = [], []
    for symbol, raw in px.groupby("symbol"):
        raw = raw.set_index("date").dropna(subset=["open", "high", "low", "close", "adj_close"])
        frames = {}
        for mode in (1, 2):
            p = {**gfs.defaults(), "mode": mode}
            frames[mode] = (p, tester.prepare(gfs, raw, p))
        ready = tester.first_ready({symbol: frames[1][1]})
        if ready is None or len(frames[1][1].loc[ready:]) < MIN_BARS:
            continue
        for mode, (p, f) in frames.items():
            for ex in ("A", "B"):
                params = {**p, "exit_mode": ex}
                for period, a, b in (("full", None, None), *tester.PERIODS):
                    start = max(pd.Timestamp(a or ready), ready)
                    out = tester.run({symbol: f}, cfg, start, b, gfs, params)
                    if out is None:
                        continue
                    res, m = out
                    rows.append({"symbol": symbol, "mode": mode, "exit": ex, "period": period, **m})
                    if period == "full" and len(res.trades):
                        trades.append(res.trades.assign(symbol=symbol, mode=mode, exit=ex))
        hold = tester.buy_and_hold(frames[1][1]["close"].loc[ready:])
        rows.append({"symbol": symbol, "mode": 0, "exit": "-", "period": "full", **hold})
    res, tr = pd.DataFrame(rows), pd.concat(trades, ignore_index=True)
    out = ROOT / "reports" / "gfs"
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "by_symbol.csv", index=False, float_format="%.5f")
    tr.to_csv(out / "trades.csv", index=False, float_format="%.5f")

    pd.set_option("display.width", 200)
    s = res[res["mode"] > 0]
    print(f"{res.symbol.nunique()} stocks")
    print(s.groupby(["mode", "exit", "period"]).agg(
        median_cagr=("cagr", "median"), median_dd=("max_drawdown", "median"), median_trades=("trades", "median"),
        stocks_traded=("trades", lambda x: (x > 0).sum()), profitable=("total_return", lambda x: (x > 0).mean()),
        invested=("exposure", "median")).round(4).to_string())
    pooled = []
    for (mode, ex), g in tr.groupby(["mode", "exit"]):
        for name, a, b in (("full", None, None), *tester.PERIODS):
            d = pd.to_datetime(g.entry_date)
            t = g[(d >= pd.Timestamp(a or d.min())) & (d <= pd.Timestamp(b or d.max()))]
            r = t["return"]
            pooled.append({"mode": mode, "exit": ex, "period": name, "trades": len(t), "win": (r > 0).mean(),
                           "avg": r.mean(), "avg_win": r[r > 0].mean(), "avg_loss": r[r <= 0].mean(),
                           "pf": r[r > 0].sum() / -r[r <= 0].sum(), "avg_R": t["R"].mean(),
                           "days": (pd.to_datetime(t.exit_date) - pd.to_datetime(t.entry_date)).dt.days.median()})
    print(pd.DataFrame(pooled).round(4).to_string(index=False))
    h = res[res["mode"] == 0]
    print(f"buy and hold: median cagr {h.cagr.median():.3f}, median dd {h.max_drawdown.median():.3f}")


if __name__ == "__main__":
    main()
