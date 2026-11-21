"""Entry/exit signals. Each function returns boolean arrays aligned to the bars.
A True at bar t means: decide at the close of t, execute at the open of t+1."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _crosses_above(s: pd.Series, level: float) -> pd.Series:
    return (s.shift(1) <= level) & (s > level)


def _crosses_below(s: pd.Series, level: float) -> pd.Series:
    return (s.shift(1) >= level) & (s < level)


def rsi_signals(rsi: pd.Series, entry_level: float = 30, exit_level: float = 70):
    return _crosses_above(rsi, entry_level), _crosses_below(rsi, exit_level)


def ema_cross_signals(fast: pd.Series, slow: pd.Series):
    diff = fast - slow
    return _crosses_above(diff, 0.0), _crosses_below(diff, 0.0)


def bbands_signals(close: pd.Series, lower: pd.Series, upper: pd.Series):
    below_lower = close < lower
    above_upper = close > upper
    entry = (below_lower.shift(1, fill_value=False)) & (close > lower)   # back above lower band
    exit_ = (above_upper.shift(1, fill_value=False)) & (close < upper)   # back below upper band
    return entry.fillna(False).to_numpy(), exit_.fillna(False).to_numpy()
