"""Prepare stock data for the portfolio version of the multi-timeframe SMA strategy and run one variant."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import talib

from ..backtest.metrics import performance
from ..backtest.mtf_sma import signals
from ..backtest.portfolio import PortfolioConfig, run_portfolio
from .mtf_sma_run import adjusted

FILTERS = ("market", "liquid10", "liquid50", "not_extended", "weekly_rising")


def prepare(raw: pd.DataFrame, period: int = 20, confirm: int = 3, swing_bars: int = 10) -> pd.DataFrame:
    """One stock's raw Yahoo bars (date index) -> frame for run_portfolio, with a column per entry filter.
    Every value on a row uses only that day's and earlier data."""
    turnover = (raw["close"] * raw["volume"]).rolling(20).median()
    d = adjusted(raw)
    s = signals(d, period, confirm)
    out = d[["open", "high", "low", "close"]].copy()
    out["entry"], out["exit_sma"] = s["entry"], s["exit"]
    out["exit_weekly"] = d["close"] < s["sma_w"]
    out["atr"] = talib.ATR(d["high"].to_numpy(float), d["low"].to_numpy(float), d["close"].to_numpy(float), 14)
    out["swing_low"] = d["low"].rolling(swing_bars).min()
    out["score"] = d["close"] / d["close"].shift(126) - 1       # 6-month return, ranks competing signals
    out["liquid10"] = turnover >= 10e7                          # median traded value >= INR 10 crore
    out["liquid50"] = turnover >= 50e7
    out["not_extended"] = d["close"] <= 1.08 * s["sma_d"]
    out["weekly_rising"] = s["sma_w"] > s["sma_w"].shift(5)
    out["sma_d"], out["sma_w"], out["sma_m"], out["volume"] = s["sma_d"], s["sma_w"], s["sma_m"], d["volume"]
    return out


def market_uptrend(index_close: pd.Series, period: int = 200) -> pd.Series:
    return index_close > index_close.rolling(period).mean()


def add_market(data: dict[str, pd.DataFrame], uptrend: pd.Series) -> None:
    for df in data.values():
        # dates without an index value take the previous one (never a later one)
        df["market"] = uptrend.astype(float).reindex(df.index, method="ffill").fillna(0).astype(bool)


@dataclass(frozen=True)
class Variant:
    cfg: PortfolioConfig = PortfolioConfig()
    filters: tuple[str, ...] = ()


def run_variant(data: dict[str, pd.DataFrame], v: Variant, start=None, end=None, costs: dict | None = None):
    if v.filters:
        unknown = set(v.filters) - set(FILTERS)
        if unknown:
            raise ValueError(f"unknown filters {unknown}")
        data = {s: df.assign(entry=df["entry"] & df[list(v.filters)].all(axis=1)) for s, df in data.items()}
    res = run_portfolio(data, v.cfg, costs, start, end)
    m = performance(res.equity, res.trades, res.exposure)
    years = (res.equity.index[-1] - res.equity.index[0]).days / 365.25
    # calendar years, and measured from the starting cash so first-day costs count
    m["total_return"] = res.equity.iloc[-1] / v.cfg.initial_cash - 1
    m["cagr"] = (1 + m["total_return"]) ** (1 / years) - 1
    m["calmar"] = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] < 0 else float("nan")
    if len(res.trades):
        r = res.trades["return"]
        m["avg_win"], m["avg_loss"] = r[r > 0].mean(), r[r <= 0].mean()
    return res, m
