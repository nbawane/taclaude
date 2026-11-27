"""The fixed test that every strategy goes through: same execution engine, costs, periods and benchmarks."""
from __future__ import annotations

import pandas as pd
import talib

from ..backtest.portfolio import PortfolioConfig
from ..strategies import Strategy
from .mtf_sma_portfolio import Variant, run_variant
from .mtf_sma_run import adjusted

PERIODS = (("2018 to 2022", None, "2022-12-31"), ("2023 to 2024", "2023-01-01", "2024-12-31"),
           ("2025 onward", "2025-01-01", None))
FEW_TRADES = 30


def prepare(strategy: Strategy, raw: pd.DataFrame, params: dict, swing_bars: int = 10) -> pd.DataFrame:
    """One stock's raw Yahoo bars (date index) -> frame for the portfolio engine plus the indicator lines."""
    bars = adjusted(raw)
    s = strategy.compute(bars, params)
    out = bars[["open", "high", "low", "close", "volume"]].join(s.drop(columns=["entry", "exit", "exit_weekly"],
                                                                       errors="ignore"))
    lines = [x.column for x in strategy.overlays + strategy.panel]
    ready = out[lines].notna().all(axis=1) if lines else pd.Series(True, index=out.index)
    out["ready"] = ready
    out["entry"] = pd.Series(s["entry"], index=bars.index).astype(bool) & ready
    out["exit_sma"] = pd.Series(s["exit"], index=bars.index).astype(bool)   # engine's name for "strategy exit"
    out["exit_weekly"] = s["exit_weekly"] if "exit_weekly" in s else False
    out["atr"] = talib.ATR(bars["high"].to_numpy(float), bars["low"].to_numpy(float),
                           bars["close"].to_numpy(float), 14)
    out["swing_low"] = bars["low"].rolling(swing_bars).min()
    out["score"] = bars["close"] / bars["close"].shift(126) - 1   # ranks competing signals: 6-month return
    return out


def first_ready(frames: dict[str, pd.DataFrame]):
    dates = [f.index[f["ready"]][0] for f in frames.values() if f["ready"].any()]
    return min(dates) if dates else None


def run(frames: dict[str, pd.DataFrame], cfg: PortfolioConfig, start=None, end=None):
    """(Result, metrics), or None if the window has too few bars."""
    if not any(len(f.loc[start:end]) > 1 for f in frames.values()):
        return None
    return run_variant(frames, Variant(cfg), start, end)


def buy_and_hold(close: pd.Series) -> dict:
    """Return, yearly return and worst fall of simply holding (no costs)."""
    close = close.dropna()
    years = (close.index[-1] - close.index[0]).days / 365.25
    total = close.iloc[-1] / close.iloc[0] - 1
    return {"total_return": total, "cagr": (1 + total) ** (1 / years) - 1 if years > 0 else float("nan"),
            "max_drawdown": float((close / close.cummax() - 1).min())}


def by_period(frames: dict, cfg: PortfolioConfig, benchmarks: dict[str, pd.Series], start, end) -> pd.DataFrame:
    """Each period is a fresh run, limited to the chosen date range."""
    rows = []
    for name, a, b in PERIODS:
        a = max(pd.Timestamp(a or start), pd.Timestamp(start))
        b = min(pd.Timestamp(b or end), pd.Timestamp(end))
        if a >= b:
            continue
        out = run(frames, cfg, a, b)
        if out is None:
            continue
        m = out[1]
        row = {"period": name, "trades": m["trades"], "cagr": m["cagr"], "max_drawdown": m["max_drawdown"],
               "win_rate": m["win_rate"]}
        for label, series in benchmarks.items():
            s = series.loc[a:b].dropna()
            if len(s) > 1:
                row[f"{label} cagr"] = buy_and_hold(s)["cagr"]
        rows.append(row)
    return pd.DataFrame(rows)


def warnings(metrics: dict, periods: pd.DataFrame, benchmarks: dict[str, dict]) -> list[str]:
    out = []
    if metrics["trades"] < FEW_TRADES:
        out.append(f"Only {metrics['trades']} closed trades (fewer than {FEW_TRADES}): too few to judge.")
    for name, b in benchmarks.items():
        if metrics["cagr"] < b["cagr"]:
            out.append(f"Yearly return {metrics['cagr']:.1%} is below {name} ({b['cagr']:.1%}).")
    if len(periods):
        last = periods.iloc[-1]
        if last["cagr"] < 0:
            out.append(f"Lost money in the most recent period ({last['period']}: {last['cagr']:.1%} a year).")
    return out
