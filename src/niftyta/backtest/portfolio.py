"""Long-only portfolio backtest: one cash account shared by many stocks, with position sizing,
stoploss, targets and trailing stops.

Order of events on each day:
  1. At the open: exits decided at the previous close, then gaps through a stop or target.
  2. At the open: new entries from the previous close's signals, strongest `score` first.
  3. During the day: stop and target. If one bar touches both, the stop is taken first.
  4. At the close: trailing stops move up, exits and new signals are noted for the next open.
Prices include slippage; costs come from config/costs.yaml. No leverage, whole shares."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .costs import buy_cost_rate, load_costs, sell_cost_rate
from .engine import Result

# columns every symbol frame must provide
FIELDS = ("open", "high", "low", "close", "entry", "exit_sma", "exit_weekly", "atr", "swing_low", "score")
EXITS = ("sma", "target", "half_trail", "atr_trail", "weekly")


@dataclass(frozen=True)
class PortfolioConfig:
    risk_pct: float = 0.01            # of equity lost if the initial stop is hit
    max_positions: int = 5
    max_position_pct: float = 0.25    # of equity in one stock
    stop: str = "atr"                 # "atr", "swing" or "none" (none: size = max_position_pct)
    stop_atr: float = 2.0
    exit: str = "sma"                 # one of EXITS
    target_r: float = 2.0             # "target": full exit; "half_trail": sell half here
    trail_atr: float = 3.0
    initial_cash: float = 100_000.0


@dataclass
class _Pos:
    j: int
    entry_date: object
    entry_px: float
    shares: int
    init_shares: int
    entry_gross: float
    entry_fee: float
    stop: float
    init_stop: float
    target: float
    best_close: float
    exit_gross: float = 0.0
    exit_fees: float = 0.0
    scaled: bool = False
    pending: str = ""                 # reason for an exit at the next open


def run_portfolio(data: dict[str, pd.DataFrame], cfg: PortfolioConfig, costs: dict | None = None,
                  start=None, end=None) -> Result:
    """data: symbol -> daily frame with FIELDS (indicators computed on the full history).
    Only bars from `start` to `end` (inclusive) are traded; each run begins flat."""
    if cfg.exit not in EXITS:
        raise ValueError(f"exit must be one of {EXITS}")
    c = costs or load_costs()
    buy_r, sell_r, slip = buy_cost_rate(c), sell_cost_rate(c), c["slippage_per_side"]
    dp = c.get("dp_charge_per_sell_inr", 0.0)

    symbols = sorted(data)
    wide = {f: pd.DataFrame({s: data[s][f] for s in symbols}).sort_index().loc[start:end] for f in FIELDS}
    dates = wide["close"].index
    o, h, l, cl, atr, swing, score = (wide[f].to_numpy(float) for f in
                                      ("open", "high", "low", "close", "atr", "swing_low", "score"))
    entry, x_sma, x_week = (wide[f].astype(float).fillna(0).to_numpy() > 0 for f in
                            ("entry", "exit_sma", "exit_weekly"))
    n = len(dates)

    cash = cfg.initial_cash
    held: dict[int, _Pos] = {}
    wanted: list[tuple[int, int]] = []        # (symbol column, signal row)
    last = np.full(len(symbols), np.nan)      # last known close
    equity, invested = np.empty(n), np.empty(n)
    trades: list[dict] = []
    prev_equity = cash

    def sell(p: _Pos, qty: int, px_raw: float, k: int, reason: str) -> None:
        nonlocal cash
        gross = qty * px_raw * (1 - slip)
        fee = gross * sell_r + dp
        cash += gross - fee
        p.shares -= qty
        p.exit_gross += gross
        p.exit_fees += fee
        if p.shares == 0:
            paid = p.entry_gross + p.entry_fee
            pnl = p.exit_gross - p.exit_fees - paid
            risk = (p.entry_px - p.init_stop) * p.init_shares
            trades.append({"symbol": symbols[p.j], "entry_date": p.entry_date, "exit_date": dates[k],
                           "shares": p.init_shares, "entry_price": p.entry_px,
                           "exit_price": p.exit_gross / p.init_shares, "stop": p.init_stop,
                           "target": p.target, "pnl": pnl, "return": pnl / paid,
                           "R": pnl / risk if np.isfinite(risk) and risk > 0 else np.nan,
                           "costs": p.entry_fee + p.exit_fees, "reason": reason})
            del held[p.j]

    def gap_exit(p: _Pos, k: int) -> None:
        j = p.j
        if o[k, j] <= p.stop:
            sell(p, p.shares, o[k, j], k, "gap stop")
        elif cfg.exit == "target" and o[k, j] >= p.target:
            sell(p, p.shares, o[k, j], k, "gap target")

    for k in range(n):
        traded = ~np.isnan(o[k]) & ~np.isnan(cl[k])
        # 1. exits at the open
        for p in list(held.values()):
            if not traded[p.j]:
                continue
            if p.pending:
                sell(p, p.shares, o[k, p.j], k, p.pending)
            else:
                gap_exit(p, k)
        # 2. entries at the open
        for j, s in sorted(wanted, key=lambda w: (-np.nan_to_num(score[w[1], w[0]], nan=-np.inf), w[0])):
            if len(held) >= cfg.max_positions:
                break
            if j in held or not traded[j]:
                continue
            px = o[k, j] * (1 + slip)
            if cfg.stop == "atr":
                stop = px - cfg.stop_atr * atr[s, j]
            elif cfg.stop == "swing":
                stop = swing[s, j]
            else:
                stop = -np.inf
            if np.isnan(stop) or o[k, j] <= stop:
                continue
            value = cfg.max_position_pct * prev_equity
            qty = int(np.floor(min(value, cash / (1 + buy_r)) / px))
            if cfg.stop != "none":
                qty = min(qty, int(np.floor(cfg.risk_pct * prev_equity / (px - stop))))
            if qty <= 0:
                continue
            gross = qty * px
            fee = gross * buy_r
            cash -= gross + fee
            target = px + cfg.target_r * (px - stop) if cfg.exit in ("target", "half_trail") else np.nan
            held[j] = _Pos(j, dates[k], px, qty, qty, gross, fee, stop, stop, target, px)
        # 3. stop and target during the day
        for p in list(held.values()):
            j = p.j
            if not traded[j]:
                continue
            if l[k, j] <= p.stop:
                sell(p, p.shares, min(p.stop, o[k, j]), k, "stop")
            elif cfg.exit == "target" and h[k, j] >= p.target:
                sell(p, p.shares, max(p.target, o[k, j]), k, "target")
            elif cfg.exit == "half_trail" and not p.scaled and h[k, j] >= p.target:
                p.scaled = True
                half = p.shares // 2
                if half:
                    sell(p, half, max(p.target, o[k, j]), k, "half at target")
                p.stop = max(p.stop, p.entry_px)
        # 4. decisions at the close
        last = np.where(traded, cl[k], last)
        for p in held.values():
            j = p.j
            if not traded[j]:
                continue
            p.best_close = max(p.best_close, cl[k, j])
            if cfg.exit == "atr_trail" or (cfg.exit == "half_trail" and p.scaled):
                level = p.best_close - cfg.trail_atr * atr[k, j]
                if not np.isnan(level):
                    p.stop = max(p.stop, level)
            if cfg.exit == "sma" and x_sma[k, j]:
                p.pending = "close below daily SMA"
            elif cfg.exit == "weekly" and x_week[k, j]:
                p.pending = "close below weekly SMA"
        value = sum(p.shares * last[p.j] for p in held.values())
        equity[k] = prev_equity = cash + value
        invested[k] = value / prev_equity if prev_equity > 0 else 0.0
        wanted = [(j, k) for j in np.flatnonzero(entry[k] & traded) if j not in held]

    still_open = [{"symbol": symbols[p.j], "entry_date": p.entry_date, "entry_price": p.entry_px,
                   "shares": p.shares, "stop": p.init_stop, "target": p.target} for p in held.values()]
    return Result(equity=pd.Series(equity, index=dates, name="equity"), trades=pd.DataFrame(trades),
                  exposure=float(invested.mean()) if n else 0.0, open_at_end=bool(held),
                  open_positions=still_open)
