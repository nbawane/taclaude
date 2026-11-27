"""Build weekly and monthly bars from stored daily bars. Nothing is fetched or invented.

Weekly bars end on Friday (or the last session of that week if Friday is a holiday).
Monthly bars end on the last calendar day of the month. The most recent bar may still be
forming; it is flagged `partial=True` so it is never mistaken for a completed bar."""
from __future__ import annotations

from datetime import date

import pandas as pd

RULES = {"1D": None, "1W": "W-FRI", "1M": "ME"}
AGG = {"open": "first", "high": "max", "low": "min", "close": "last",
       "adj_close": "last", "volume": "sum",
       # delivery quantity is unknown before 2020: an all-blank period stays blank, never 0
       "deliv_qty": lambda s: s.sum(min_count=1)}


def resample_ohlcv(daily: pd.DataFrame, timeframe: str, as_of: date | None = None) -> pd.DataFrame:
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
        # The latest bar is still forming if its period has not ended yet. A period that has ended
        # is complete even if its calendar end was a holiday (e.g. a week whose Friday was closed).
        # Data that stops more than 2 calendar days short of the period end is stale: flag it.
        today = pd.Timestamp(as_of or date.today())
        last_session, period_end = daily.index.max(), out.index[-1]
        still_open = today <= period_end
        stale = (period_end - last_session).days > 2
        out.iloc[-1, out.columns.get_loc("partial")] = bool(last_session < period_end and (still_open or stale))
    return out


def multi_timeframe(daily: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {tf: resample_ohlcv(daily, tf) for tf in ("1D", "1W", "1M")}
