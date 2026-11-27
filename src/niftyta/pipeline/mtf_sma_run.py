"""Run the multi-timeframe SMA strategy on one stock. Shared by the report script and the dashboard."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..backtest.engine import run_backtest
from ..backtest.metrics import performance
from ..backtest.mtf_sma import signals
from ..backtest.runner import IN_SAMPLE_FRACTION

STRAT, DAILY_ONLY, HOLD = "Monthly + weekly + daily", "Daily SMA only", "Buy and hold"


def adjusted(df: pd.DataFrame) -> pd.DataFrame:
    """Yahoo bars scaled to split- and dividend-adjusted prices."""
    f = df["adj_close"] / df["close"]
    return df.assign(**{c: df[c] * f for c in ("open", "high", "low")}, close=df["adj_close"], deliv_qty=np.nan)


def run_symbol(symbol, df, period, confirm, min_bars):
    """Return (metric rows, equity by strategy, trade frames, bars, signals, open entries), or None if too short."""
    sig = {STRAT: signals(df, period, confirm, htf=True), DAILY_ONLY: signals(df, period, confirm, htf=False)}
    ready = sig[STRAT]["ready"].to_numpy()
    if not ready.any() or len(df) - ready.argmax() < min_bars:
        return None
    start = int(ready.argmax())
    d = df.iloc[start:]
    r = d["close"] / d["close"].shift()
    big_jump = bool(((r < 0.65) | (r > 1.54)).any())
    split = int(len(d) * IN_SAMPLE_FRACTION)
    rows, equity, trades, open_entries = [], {}, [], {}
    for part, (a, b) in {"full": (0, len(d)), "in_sample": (0, split), "out_of_sample": (split, len(d))}.items():
        sub = d.iloc[a:b]
        hold = np.zeros(len(sub), bool)
        hold[0] = True
        runs = {k: (v["entry"].to_numpy()[start:][a:b], v["exit"].to_numpy()[start:][a:b]) for k, v in sig.items()}
        runs[HOLD] = (hold, np.zeros(len(sub), bool))
        for name, (en, ex) in runs.items():
            res = run_backtest(sub, en, ex)
            rows.append({"symbol": symbol, "strategy": name, "period": part, "from": sub.index[0].date(),
                         "to": sub.index[-1].date(), "big_price_jump": big_jump,
                         **performance(res.equity, res.trades, res.exposure)})
            if part != "full":
                continue
            equity[name] = res.equity
            if name != HOLD and len(res.trades):
                trades.append(res.trades.assign(symbol=symbol, strategy=name))
            if name != HOLD and res.open_at_end:
                open_entries[name] = open_entry(sub, en, res.trades)
    return rows, equity, trades, d, sig[STRAT].iloc[start:], open_entries


def open_entry(df: pd.DataFrame, entries: np.ndarray, trades: pd.DataFrame):
    """(date, price before slippage) of the position still open at the end of the data."""
    first = df.index.get_loc(trades["exit_date"].iloc[-1]) if len(trades) else 0
    i = first + int(np.argmax(entries[first:-1])) + 1   # filled at the next open
    return df.index[i], float(df["open"].iloc[i])
