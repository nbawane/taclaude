"""Run all strategies on one bar series at one timeframe, over the full period and
in-sample / out-of-sample splits. Parameters are fixed (no tuning on the test period)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..indicators.core import compute_indicators
from .engine import Result, run_backtest
from .metrics import performance
from .strategies import bbands_signals, ema_cross_signals, rsi_signals

IN_SAMPLE_FRACTION = 0.7
BUY_AND_HOLD = "Buy and hold"


def strategy_signals(df: pd.DataFrame, ind: pd.DataFrame, strat: dict) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    r = strat["rsi"]
    rsi_in, rsi_out = rsi_signals(ind["rsi_14"], r["entry_cross_above"], r["exit_cross_below"])
    ema_in, ema_out = ema_cross_signals(ind["ema_9"], ind["ema_21"])
    bb_in, bb_out = bbands_signals(df["close"], ind["bb_lower_20_2"], ind["bb_upper_20_2"])
    f = lambda s: s.fillna(False).to_numpy(bool)  # noqa: E731
    return {
        "RSI(14) 30/70": (f(rsi_in), f(rsi_out)),
        "EMA 9/21 cross": (f(ema_in), f(ema_out)),
        "Bollinger 20,2": (bb_in, bb_out),
    }


@dataclass
class PeriodResult:
    period: str
    strategy: str
    result: Result
    metrics: dict
    start: pd.Timestamp
    end: pd.Timestamp


def run_all(df: pd.DataFrame, params: dict, strat: dict, periods_per_year: int = 252) -> list[PeriodResult]:
    """df: bars for one timeframe (already partial-bar filtered). Indicators use the full
    series; each period's trades are simulated only inside that period."""
    ind = compute_indicators(df, params)
    sigs = strategy_signals(df, ind, strat)
    split = int(len(df) * IN_SAMPLE_FRACTION)
    periods = {"full": (0, len(df)), "in_sample": (0, split), "out_of_sample": (split, len(df))}
    out = []
    for period, (a, b) in periods.items():
        sub = df.iloc[a:b]
        for name, (ent, ex) in sigs.items():
            res = run_backtest(sub, ent[a:b].copy(), ex[a:b].copy())
            out.append(_pack(period, name, res, sub, periods_per_year))
        bh_e = np.zeros(len(sub), bool); bh_e[0] = True
        out.append(_pack(period, BUY_AND_HOLD, run_backtest(sub, bh_e, np.zeros(len(sub), bool)), sub, periods_per_year))
    return out


def _pack(period, name, res, sub, periods_per_year):
    m = performance(res.equity, res.trades, res.exposure, periods_per_year)
    return PeriodResult(period, name, res, m, sub.index.min(), sub.index.max())


def summary_frame(results: list[PeriodResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({"period": r.period, "strategy": r.strategy, **r.metrics,
                     "open_at_end": r.result.open_at_end,
                     "from": r.start.date(), "to": r.end.date()})
    return pd.DataFrame(rows)
