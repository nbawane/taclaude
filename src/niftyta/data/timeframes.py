"""Build weekly and monthly bars from stored daily bars. Nothing is fetched or invented.

Weekly bars end on Friday (or the last session of that week if Friday is a holiday).
Monthly bars end on the last calendar day of the month. The most recent bar may still be
forming; it is flagged `partial=True` so it is never mistaken for a completed bar."""
from __future__ import annotations

import pandas as pd

RULES = {"1D": None, "1W": "W-FRI", "1M": "ME"}
AGG = {"open": "first", "high": "max", "low": "min", "close": "last",
       "adj_close": "last", "volume": "sum", "deliv_qty": "sum"}


def resample_ohlcv(daily: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """daily: one symbol, indexed by date, with open/high/low/close/adj_close/volume/deliv_qty."""
    if timeframe not in RULES:
        raise ValueError(f"timeframe must be one of {list(RULES)}")
    if RULES[timeframe] is None:
        out = daily.copy()
    else:
        out = daily.resample(RULES[timeframe], label="right", closed="right").agg(AGG)
        out = out.dropna(subset=["close"])  # periods with no sessions at all
    out["partial"] = False
    if timeframe != "1D" and len(out):
        # the latest period is still forming if the data ends before its calendar end
        out.iloc[-1, out.columns.get_loc("partial")] = daily.index.max() < out.index[-1]
    return out


def multi_timeframe(daily: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {tf: resample_ohlcv(daily, tf) for tf in ("1D", "1W", "1M")}
