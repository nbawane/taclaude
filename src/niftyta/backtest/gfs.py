"""Bullish GFS (Grandfather-Father-Son) + RSI divergence. Spec (source of truth): docs/strategies/gfs_spec.md. Choices: docs/strategies/gfs_interpretation.md.

Lookahead rules
- Higher-timeframe RSI for a Son bar dated d = RSI of the last higher-timeframe bar whose
  period end is strictly before d. Forming (partial) bars are excluded.
- A swing low at bar p is confirmed at bar p + n. It is only used from that bar onward.
- Orders decided at bar t's close fill at bar t+1 or later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import talib

from ..data.timeframes import resample_ohlcv
from .costs import buy_cost_rate, load_costs, sell_cost_rate
from .engine import Result


# ---------- timeframes and higher-timeframe RSI ----------
def closed_bars(daily: pd.DataFrame, tf: str) -> pd.DataFrame:
    bars = resample_ohlcv(daily, tf)
    return bars[~bars["partial"]]


def rsi_series(bars: pd.DataFrame, period: int) -> pd.Series:
    return pd.Series(talib.RSI(bars["close"].to_numpy(float), timeperiod=period), index=bars.index)


def last_closed_value(htf: pd.Series, son_dates: pd.DatetimeIndex) -> np.ndarray:
    """For each son date d: value at the last htf label strictly before d (NaN if none)."""
    labels = htf.index.values
    pos = np.searchsorted(labels, son_dates.values, side="left") - 1
    out = np.full(len(son_dates), np.nan)
    ok = pos >= 0
    out[ok] = htf.to_numpy()[pos[ok]]
    return out


# ---------- swing lows and divergence ----------
def pivot_lows(low: np.ndarray, n: int) -> np.ndarray:
    """piv[p] True if low[p] is the strict minimum of low[p-n .. p+n]. Known only at p+n."""
    piv = np.zeros(len(low), bool)
    for p in range(n, len(low) - n):
        w = low[p - n:p + n + 1]
        piv[p] = low[p] == w.min() and (w == low[p]).sum() == 1
    return piv


def divergence_at(t: int, low, rsi, piv, cfg) -> bool:
    n = cfg["divergence_swing_bars"]
    # second swing low: confirmed (p2 + n <= t) and within the last `divergence_recent` bars
    for p2 in range(t - n, t - cfg["divergence_recent"] - 1, -1):
        if p2 < 0 or not piv[p2]:
            continue
        if not (35 <= rsi[p2] <= 45):  # second low sits in the pullback zone
            continue
        for p1 in range(p2 - cfg["divergence_min_gap"], p2 - cfg["divergence_max_gap"] - 1, -1):
            if p1 < 0 or not piv[p1]:
                continue
            if low[p2] < low[p1] and rsi[p2] > rsi[p1]:
                return True
    return False


# ---------- signals ----------
@dataclass
class Signals:
    gate: np.ndarray
    mode1: np.ndarray
    mode2: np.ndarray
    son_rsi: np.ndarray
    gf_rsi: np.ndarray
    f_rsi: np.ndarray


def build_signals(daily: pd.DataFrame, cfg: dict) -> Signals:
    son = closed_bars(daily, cfg["son_tf"])
    rsi_p = cfg["rsi_period"]
    son_rsi = rsi_series(son, rsi_p).to_numpy()
    gf = last_closed_value(rsi_series(closed_bars(daily, cfg["grandfather_tf"]), rsi_p), son.index)
    f = last_closed_value(rsi_series(closed_bars(daily, cfg["father_tf"]), rsi_p), son.index)
    o, h, l, c = (son[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(son)

    in_zone = (son_rsi >= cfg["pullback_low"]) & (son_rsi <= cfg["pullback_high"])
    pullback = np.zeros(n, bool)
    for k in range(n):
        lo = max(0, k - cfg["pullback_lookback"] + 1)
        pullback[k] = in_zone[lo:k + 1].any()
    htf_ok = (gf > cfg["htf_rsi_min"]) & (f > cfg["htf_rsi_min"])
    gate = htf_ok & pullback & ~np.isnan(son_rsi)
    bullish = c > o

    mode1 = np.zeros(n, bool)
    mode1[1:] = gate[1:] & (son_rsi[1:] > son_rsi[:-1]) & bullish[1:]

    piv = pivot_lows(l, cfg["divergence_swing_bars"])
    mode2 = np.zeros(n, bool)
    for k in range(n):
        if gate[k] and bullish[k] and divergence_at(k, l, son_rsi, piv, cfg):
            mode2[k] = True
    return Signals(gate, mode1, mode2, son_rsi, gf, f)


# ---------- simulator ----------
@dataclass
class _Pos:
    entry_i: int
    entry_date: object
    entry_px: float
    sl: float
    target: float
    init_shares: int
    shares: int
    entry_gross: float
    entry_fee: float
    risk: float
    exit_gross: float = 0.0
    exit_fees: float = 0.0
    scaled: bool = False
    pending_scale: bool = False
    pending_rest: bool = False
    reasons: list = field(default_factory=list)


def simulate(daily: pd.DataFrame, sig_trigger: np.ndarray, cfg: dict, exit_mode: str,
             costs: dict | None = None, initial_cash: float = 100_000.0,
             rsi: np.ndarray | None = None) -> Result:
    """sig_trigger: boolean per Son bar (mode 1 or mode 2 signal). exit_mode: 'A' or 'B'.
    rsi: Son RSI aligned to the Son bars of `daily`. Pass RSI computed on the FULL history when
    simulating a slice, otherwise Wilder smoothing restarts at the slice and mode B exits differ."""
    c_ = costs or load_costs()
    buy_r, sell_r, slip = buy_cost_rate(c_), sell_cost_rate(c_), c_["slippage_per_side"]
    dp = c_.get("dp_charge_per_sell_inr", 0.0)
    son = closed_bars(daily, cfg["son_tf"])
    o, h, l, c = (son[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    rsi = rsi_series(son, cfg["rsi_period"]).to_numpy() if rsi is None else np.asarray(rsi, float)
    dates = son.index
    n = len(son)
    rr, scale_rsi, rest_rsi = cfg["exit_rr"], cfg["scale_rsi"], cfg["rest_exit_rsi"]
    valid = cfg["alert_valid_bars"]

    cash = initial_cash
    pos: _Pos | None = None
    pending: dict | None = None
    trades: list[dict] = []
    equity = np.empty(n)
    in_pos = 0

    def sell(p: _Pos, qty: int, px_raw: float, k: int) -> None:
        nonlocal cash
        px = px_raw * (1 - slip)
        gross = qty * px
        fee = gross * sell_r + dp
        cash += gross - fee
        p.shares -= qty
        p.exit_gross += gross
        p.exit_fees += fee

    def close_trade(p: _Pos, k: int, reason: str) -> None:
        nonlocal pos
        trades.append(_finish(p, dates[k], reason))
        pos = None

    for k in range(n):
        # 1. orders that were set at the previous close execute at this open
        if pos is not None and pos.pending_scale and pos.shares > 0:
            qty = int(np.floor(pos.shares * cfg["scale_fraction"]))
            if qty > 0:
                sell(pos, qty, o[k], k)
                pos.reasons.append("scale-out 50%")
            pos.scaled = True
            pos.sl = pos.entry_px  # break-even
            pos.pending_scale = False
        if pos is not None and pos.pending_rest and pos.shares > 0:
            sell(pos, pos.shares, o[k], k)
            pos.reasons.append("RSI below 55")
            close_trade(pos, k, "+".join(pos.reasons))
        if pos is not None and pos.shares == 0:
            close_trade(pos, k, "+".join(pos.reasons))

        # 2. entry from a live buy-stop alert (only when flat)
        if pos is None and pending is not None and pending["first"] <= k <= pending["expires"]:
            stop, sl = pending["stop"], pending["sl"]
            filled_px = None
            if o[k] >= stop:
                filled_px = o[k]          # gapped above the stop
            elif o[k] <= sl or l[k] <= sl:
                pending = None            # alert low breached first: cancel
            elif h[k] >= stop:
                filled_px = stop
            if filled_px is not None:
                px = filled_px * (1 + slip)
                shares = int(np.floor((cash / (1 + buy_r)) / px))
                if shares > 0:
                    gross = shares * px
                    fee = gross * buy_r
                    cash -= gross + fee
                    risk = px - sl
                    pos = _Pos(entry_i=k, entry_date=dates[k], entry_px=px, sl=sl, target=px + rr * risk,
                               init_shares=shares, shares=shares, entry_gross=gross,
                               entry_fee=fee, risk=risk)
                    pending = None
            if pending is not None and k >= pending["expires"]:
                pending = None

        # 3. exits on this bar (stop first if both stop and target are touched)
        if pos is not None and pos.shares > 0:
            if o[k] <= pos.sl:
                sell(pos, pos.shares, o[k], k); pos.reasons.append("gap stop")
            elif l[k] <= pos.sl:
                sell(pos, pos.shares, pos.sl, k); pos.reasons.append("stop")
            elif exit_mode == "A" and o[k] >= pos.target:
                sell(pos, pos.shares, o[k], k); pos.reasons.append("gap target")
            elif exit_mode == "A" and h[k] >= pos.target:
                sell(pos, pos.shares, pos.target, k); pos.reasons.append("target 2.5R")
            if pos.shares == 0:
                close_trade(pos, k, "+".join(pos.reasons))

        # 4. decisions at this close (they execute next open)
        if pos is not None and pos.shares > 0 and exit_mode == "B" and not np.isnan(rsi[k]):
            if not pos.scaled and rsi[k] >= scale_rsi:
                pos.pending_scale = True
            if pos.scaled and rsi[k] < rest_rsi:
                pos.pending_rest = True

        # 5. new alert: only when flat and no live alert
        if pos is None and pending is None and sig_trigger[k]:
            pending = {"first": k + 1, "expires": k + valid, "stop": h[k], "sl": l[k]}

        equity[k] = cash + (pos.shares * c[k] if pos is not None else 0.0)
        if pos is not None:
            in_pos += 1

    open_at_end = pos is not None
    if open_at_end:  # mark to market only
        equity[-1] = cash + pos.shares * c[-1]
    tr = pd.DataFrame(trades)
    return Result(equity=pd.Series(equity, index=dates, name="equity"), trades=tr,
                  exposure=in_pos / n if n else 0.0, open_at_end=open_at_end)


def _finish(p: _Pos, exit_date, reason: str) -> dict:
    exit_px = p.exit_gross / p.init_shares
    pnl = p.exit_gross - p.exit_fees - p.entry_gross - p.entry_fee
    return {"entry_date": p.entry_date, "exit_date": exit_date, "shares": p.init_shares,
            "entry_price": p.entry_px, "exit_price": exit_px, "pnl": pnl,
            "return": pnl / (p.entry_gross + p.entry_fee),
            "R": pnl / (p.risk * p.init_shares) if p.risk > 0 else np.nan,
            "costs": p.entry_fee + p.exit_fees, "reason": reason, "stop": p.entry_px - p.risk,
            "target": p.target}
