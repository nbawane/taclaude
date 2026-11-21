"""Data-quality checks. Problems are reported or dropped, never filled or invented."""
from __future__ import annotations

import pandas as pd

from .provider import COLUMNS


def validate_day(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Row-level checks on one day's bars (indexed by symbol, with a 'date' column)."""
    out = df.reset_index()
    rows_in = len(out)
    key = ["symbol", "date"]
    dup = out.duplicated(subset=key, keep="last")
    out = out[~dup]

    ohlc = ["open", "high", "low", "close"]
    bad = out[ohlc].isna().any(axis=1) | (out[ohlc] <= 0).any(axis=1)
    bad |= out["high"] < out[["open", "close", "low"]].max(axis=1)
    bad |= out["low"] > out[["open", "close", "high"]].min(axis=1)
    out = out[~bad]

    stats = {"rows_in": rows_in, "duplicates_removed": int(dup.sum()),
             "invalid_dropped": int(bad.sum()), "rows_out": len(out)}
    return out.set_index("symbol")[["date"] + COLUMNS], stats


def symbol_gaps(symbol_dates: pd.DatetimeIndex, trading_calendar: pd.DatetimeIndex) -> list[str]:
    """Trading sessions inside a stock's own range that have no bar for it.
    Reported only (e.g. suspension, trading halt); nothing is filled."""
    if len(symbol_dates) == 0:
        return []
    window = trading_calendar[(trading_calendar >= symbol_dates.min()) &
                              (trading_calendar <= symbol_dates.max())]
    return [d.strftime("%Y-%m-%d") for d in window.difference(symbol_dates)]
