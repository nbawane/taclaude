import numpy as np
import pandas as pd
import vectorbt as vbt

from niftyta.backtest.costs import buy_cost_rate, sell_cost_rate
from niftyta.backtest.engine import run_backtest
from niftyta.backtest.strategies import bbands_signals, ema_cross_signals, rsi_signals

ZERO = {"brokerage_per_order_inr": 0, "exchange_txn_charge": 0, "sebi_fee": 0, "gst_rate": 0,
        "stamp_duty_buy": 0, "stt_delivery": 0, "slippage_per_side": 0}
REAL = {"brokerage_per_order_inr": 0, "exchange_txn_charge": 0.0000297, "sebi_fee": 0.000001,
        "gst_rate": 0.18, "stamp_duty_buy": 0.00015, "stt_delivery": 0.001, "slippage_per_side": 0.0005}


def bars(n=300, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.002, n))
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.01,
                         "low": np.minimum(open_, close) * 0.99, "close": close,
                         "adj_close": close, "volume": 1e6, "deliv_qty": 1e5},
                        index=pd.bdate_range("2020-01-01", periods=n))


def test_fill_happens_at_next_open_not_signal_close():
    df = bars(10)
    entries = np.zeros(10, bool); entries[2] = True
    exits = np.zeros(10, bool); exits[6] = True
    res = run_backtest(df, entries, exits, costs=ZERO, initial_cash=1000)
    t = res.trades.iloc[0]
    assert t["entry_date"] == df.index[3] and t["entry_price"] == df["open"].iloc[3]
    assert t["exit_date"] == df.index[7] and t["exit_price"] == df["open"].iloc[7]


def test_hand_calculated_trade_with_indian_costs():
    df = bars(10)
    df["open"] = 100.0
    entries = np.zeros(10, bool); entries[0] = True
    exits = np.zeros(10, bool); exits[4] = True
    res = run_backtest(df, entries, exits, costs=REAL, initial_cash=100_000)
    buy_r, sell_r = buy_cost_rate(REAL), sell_cost_rate(REAL)
    px_in, px_out = 100 * (1 + 0.0005), 100 * (1 - 0.0005)
    shares = np.floor((100_000 / (1 + buy_r)) / px_in)
    gross_in, gross_out = shares * px_in, shares * px_out
    cost = gross_in * buy_r + gross_out * sell_r
    expected_pnl = gross_out - gross_in - cost
    assert res.trades.iloc[0]["shares"] == shares
    assert abs(res.trades.iloc[0]["pnl"] - expected_pnl) < 1e-6
    # STT is on the sell side only, stamp duty on the buy side only; exchange/GST are on both
    assert abs((sell_r - buy_r) - (REAL["stt_delivery"] - REAL["stamp_duty_buy"])) < 1e-12


def test_costs_reduce_return():
    df = bars(300)
    rsi = pd.Series(np.r_[np.full(14, 50.0), np.linspace(20, 80, 286)], index=df.index)
    en, ex = rsi_signals(rsi)
    free = run_backtest(df, en.fillna(False).to_numpy(), ex.fillna(False).to_numpy(), costs=ZERO)
    paid = run_backtest(df, en.fillna(False).to_numpy(), ex.fillna(False).to_numpy(), costs=REAL)
    assert paid.equity.iloc[-1] < free.equity.iloc[-1]


def test_matches_vectorbt_when_costs_are_zero():
    df = bars(400, seed=7)
    ind_close = df["close"]
    fast = ind_close.rolling(9).mean(); slow = ind_close.rolling(21).mean()
    en, ex = ema_cross_signals(fast, slow)
    en = en.fillna(False).to_numpy(); ex = ex.fillna(False).to_numpy()
    mine = run_backtest(df, en, ex, costs=ZERO, initial_cash=100_000)
    # vectorbt: orders at the open of the bar AFTER the signal (shift signals by one bar)
    en_s = pd.Series(en, index=df.index).shift(1, fill_value=False)
    ex_s = pd.Series(ex, index=df.index).shift(1, fill_value=False)
    pf = vbt.Portfolio.from_signals(df["open"], en_s, ex_s, init_cash=100_000, size=np.inf,
                                    size_granularity=1, fees=0, slippage=0)
    assert len(mine.trades) == pf.trades.count()
    assert abs((mine.equity.iloc[-1] / 100_000 - 1) - pf.total_return()) < 0.01  # same return, within 1%


def test_bbands_signal_definition():
    close = pd.Series([10, 8, 9.5, 11, 12], dtype=float)
    lower = pd.Series([9, 9, 9, 9, 9], dtype=float)
    upper = pd.Series([13, 13, 13, 13, 11], dtype=float)
    en, ex = bbands_signals(close, lower, upper)
    assert en.tolist() == [False, False, True, False, False]  # 8 below lower, 9.5 back above at idx 2


def test_no_look_ahead_in_signals():
    """Signals on bars up to t must not change when future bars are removed."""
    from niftyta.indicators.core import compute_indicators, load_params
    df = bars(400, seed=3)
    p = load_params()
    cut = 300
    full_ind = compute_indicators(df, p)
    part_ind = compute_indicators(df.iloc[:cut], p)
    rsi_full, _ = rsi_signals(full_ind["rsi_14"])
    rsi_part, _ = rsi_signals(part_ind["rsi_14"])
    pd.testing.assert_series_equal(rsi_full.iloc[:cut].fillna(False), rsi_part.fillna(False))
    en_f, _ = bbands_signals(df["close"], full_ind["bb_lower_20_2"], full_ind["bb_upper_20_2"])
    en_p, _ = bbands_signals(df["close"].iloc[:cut], part_ind["bb_lower_20_2"], part_ind["bb_upper_20_2"])
    assert (en_f[:cut] == en_p).all()
