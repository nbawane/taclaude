"""Long-only, one position at a time. Signals at close of t; fills at open of t+1.
Costs: buy-side and sell-side charges from costs.yaml, plus slippage on each fill price."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .costs import buy_cost_rate, load_costs, sell_cost_rate


@dataclass
class Result:
    equity: pd.Series
    trades: pd.DataFrame
    exposure: float           # fraction of bars with an open position
    open_at_end: bool
    open_positions: list = field(default_factory=list)   # filled by the portfolio engine


def run_backtest(df: pd.DataFrame, entries: np.ndarray, exits: np.ndarray,
                 costs: dict | None = None, initial_cash: float = 100_000.0) -> Result:
    c = costs or load_costs()
    buy_rate, sell_rate, slip = buy_cost_rate(c), sell_cost_rate(c), c["slippage_per_side"]
    o = df["open"].to_numpy(float)
    cl = df["close"].to_numpy(float)
    n = len(df)
    cash, shares = initial_cash, 0.0
    equity = np.empty(n)
    trades, entry_px, entry_date, entry_cost = [], None, None, 0.0
    in_pos_bars = 0
    entries = np.asarray(entries, bool)
    exits = np.asarray(exits, bool)

    for t in range(n):
        if t + 1 < n:  # orders decided at t fill at t+1 open
            if shares == 0 and entries[t]:
                px = o[t + 1] * (1 + slip)
                budget = cash / (1 + buy_rate)
                shares = np.floor(budget / px)
                if shares > 0:
                    gross = shares * px
                    fee = gross * buy_rate
                    cash -= gross + fee
                    entry_px, entry_date, entry_cost = px, df.index[t + 1], fee
            elif shares > 0 and exits[t]:
                px = o[t + 1] * (1 - slip)
                gross = shares * px
                fee = gross * sell_rate
                cash += gross - fee
                trades.append(_trade(df, entry_date, df.index[t + 1], entry_px, px, shares,
                                     entry_cost + fee, gross))
                shares = 0.0
        equity[t] = cash + shares * cl[t]
        if shares > 0:
            in_pos_bars += 1

    open_at_end = shares > 0  # still held at the end: marked to market in equity, not a closed trade
    tr = pd.DataFrame(trades)
    return Result(equity=pd.Series(equity, index=df.index, name="equity"), trades=tr,
                  exposure=in_pos_bars / n if n else 0.0, open_at_end=open_at_end)


def _trade(df, entry_date, exit_date, entry_px, exit_px, shares, total_cost, gross_exit):
    gross_entry = shares * entry_px
    pnl = (shares * exit_px) - gross_entry - total_cost
    return {"entry_date": entry_date, "exit_date": exit_date, "shares": int(shares),
            "entry_price": entry_px, "exit_price": exit_px, "costs": total_cost,
            "pnl": pnl, "return": pnl / gross_entry}
