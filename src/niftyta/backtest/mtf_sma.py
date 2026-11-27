"""Multi-timeframe SMA breakout (long only).

Entry (decided at a daily close, filled at the next open):
  - the close has been above the daily SMA for exactly `confirm_days` sessions in a row, and
  - the close is above the SMA of the last COMPLETED weekly and monthly candles.
Exit: close below the daily SMA, filled at the next open.
Parameters: config/strategies.yaml (mtf_sma)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .gfs import closed_bars, last_closed_value


def streak(flags: np.ndarray) -> np.ndarray:
    """Length of the run of True values ending at each position."""
    out = np.zeros(len(flags), int)
    run = 0
    for i, f in enumerate(flags):
        run = run + 1 if f else 0
        out[i] = run
    return out


def signals(daily: pd.DataFrame, period: int = 20, confirm_days: int = 3, htf: bool = True) -> pd.DataFrame:
    """daily: one symbol, DatetimeIndex, open/high/low/close/adj_close/volume/deliv_qty (already adjusted).
    Returns columns sma_d, sma_w, sma_m, entry, exit, ready (all three SMAs exist)."""
    close = daily["close"]
    out = pd.DataFrame(index=daily.index)
    out["sma_d"] = close.rolling(period).mean()
    for name, tf in (("sma_w", "1W"), ("sma_m", "1M")):
        bars = closed_bars(daily, tf)
        out[name] = last_closed_value(bars["close"].rolling(period).mean(), daily.index)
    out["ready"] = out[["sma_d", "sma_w", "sma_m"]].notna().all(axis=1)
    trigger = streak((close > out["sma_d"]).to_numpy()) == confirm_days
    if htf:
        trigger &= ((close > out["sma_w"]) & (close > out["sma_m"])).to_numpy()
    out["entry"] = trigger
    out["exit"] = (close < out["sma_d"]).to_numpy()
    return out
