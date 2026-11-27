import numpy as np
import pandas as pd
import pytest

from niftyta.backtest.engine import run_backtest
from niftyta.backtest.portfolio import PortfolioConfig, run_portfolio

FREE = {"exchange_txn_charge": 0, "sebi_fee": 0, "gst_rate": 0, "stamp_duty_buy": 0, "stt_delivery": 0,
        "slippage_per_side": 0, "dp_charge_per_sell_inr": 0}


def frame(bars, entry_at=(0,), exit_at=(), atr=5.0, score=1.0):
    """bars: list of (open, high, low, close)."""
    idx = pd.bdate_range("2024-01-01", periods=len(bars))
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx, dtype=float)
    df["entry"] = [i in entry_at for i in range(len(df))]
    df["exit_sma"] = [i in exit_at for i in range(len(df))]
    df["exit_weekly"] = False
    df["atr"], df["swing_low"], df["score"] = atr, 90.0, score
    return df


FLAT = (100, 101, 99, 100)


def test_size_comes_from_risk_and_stop_distance():
    # 1% of 100,000 = 1,000 at risk; stop 2 x ATR 5 = 10 below entry 100 -> 100 shares
    r = run_portfolio({"A": frame([FLAT, FLAT, (100, 101, 89, 95)])}, PortfolioConfig(), FREE)
    t = r.trades.iloc[0]
    assert (t.shares, t.stop, t.exit_price, t.reason) == (100, 90, 90, "stop")
    assert t.pnl == -1000 and t.R == -1 and r.equity.iloc[-1] == 99_000


def test_position_cap_limits_size():
    r = run_portfolio({"A": frame([FLAT, FLAT, (100, 101, 80, 95)], atr=0.5)}, PortfolioConfig(), FREE)
    assert r.trades.iloc[0].shares == 250   # 25% of equity, although risk alone would allow 1,000


def test_gap_through_stop_fills_at_open():
    r = run_portfolio({"A": frame([FLAT, FLAT, (80, 82, 79, 81)])}, PortfolioConfig(), FREE)
    assert r.trades.iloc[0].exit_price == 80 and r.trades.iloc[0].reason == "gap stop"


def test_stop_is_taken_before_target_on_the_same_bar():
    r = run_portfolio({"A": frame([FLAT, FLAT, (100, 125, 89, 110)])}, PortfolioConfig(exit="target"), FREE)
    assert r.trades.iloc[0].reason == "stop"


def test_target_two_times_risk():
    r = run_portfolio({"A": frame([FLAT, FLAT, (105, 125, 104, 110)])}, PortfolioConfig(exit="target"), FREE)
    assert r.trades.iloc[0].exit_price == 120 and r.trades.iloc[0].R == 2


def test_half_at_target_then_stop_at_entry():
    bars = [FLAT, FLAT, (105, 121, 104, 110), (110, 111, 99, 100)]
    r = run_portfolio({"A": frame(bars)}, PortfolioConfig(exit="half_trail", trail_atr=50), FREE)
    assert r.trades.iloc[0].pnl == 50 * 20 + 50 * 0


def test_trailing_stop_uses_only_earlier_closes():
    bars = [FLAT, FLAT, (100, 131, 100, 130), (130, 131, 114, 116)]
    r = run_portfolio({"A": frame(bars)}, PortfolioConfig(exit="atr_trail"), FREE)
    assert r.trades.iloc[0].exit_price == 115   # 130 - 3 x 5, active from the next day


def test_slots_go_to_the_highest_score():
    data = {"A": frame([FLAT] * 3, score=1), "B": frame([FLAT] * 3, score=2)}
    r = run_portfolio(data, PortfolioConfig(max_positions=1), FREE)
    assert r.open_at_end and r.equity.iloc[-1] == 100_000
    r = run_portfolio({"A": frame([FLAT] * 2 + [(80, 80, 80, 80)], score=1), "B": data["B"]},
                      PortfolioConfig(max_positions=1), FREE)
    assert r.trades.empty                      # A (lower score) was never bought


def test_cash_is_never_negative_and_costs_are_charged():
    costs = {**FREE, "stt_delivery": 0.001, "dp_charge_per_sell_inr": 15.34}
    data = {s: frame([FLAT, FLAT, (100, 101, 89, 95)], atr=0.5) for s in "ABCDE"}
    r = run_portfolio(data, PortfolioConfig(max_position_pct=0.5), costs)
    assert (r.trades.shares * r.trades.entry_price).sum() <= 100_000
    assert r.trades.costs.iloc[0] > 15.34


def random_frame(seed, n=400):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    opn = close * (1 + rng.normal(0, 0.005, n))
    df = pd.DataFrame({"open": opn, "high": np.maximum(opn, close) * 1.01,
                       "low": np.minimum(opn, close) * 0.99, "close": close},
                      index=pd.bdate_range("2020-01-01", periods=n))
    df["entry"], df["exit_sma"] = rng.random(n) < 0.05, rng.random(n) < 0.08
    df["exit_weekly"], df["atr"] = False, close * 0.02
    df["swing_low"], df["score"] = df["low"].rolling(10).min(), rng.random(n)
    return df


def test_matches_single_stock_engine_when_all_in_without_stop():
    df = random_frame(1)
    costs = {**FREE, "slippage_per_side": 0.0005, "stt_delivery": 0.001, "stamp_duty_buy": 0.00015}
    a = run_backtest(df, df.entry.to_numpy(), df.exit_sma.to_numpy(), costs)
    b = run_portfolio({"A": df}, PortfolioConfig(stop="none", max_positions=1, max_position_pct=1.0), costs)
    assert len(a.trades) == len(b.trades) > 5
    cols = ["entry_date", "exit_date", "shares", "entry_price", "exit_price", "pnl"]
    pd.testing.assert_frame_equal(a.trades[cols], b.trades[cols], check_dtype=False)
    # daily values differ only on signal days: engine.py books the next open's trade one bar early
    order_days = df.entry | df.exit_sma
    np.testing.assert_allclose(a.equity[~order_days], b.equity[~order_days])


@pytest.mark.parametrize("exit_", ["sma", "target", "half_trail", "atr_trail"])
def test_no_look_ahead(exit_):
    data = {s: random_frame(i) for i, s in enumerate("ABCDEFGH")}
    cfg = PortfolioConfig(exit=exit_)
    full = run_portfolio(data, cfg, FREE)
    cut = full.equity.index[250]
    part = run_portfolio({s: d.loc[:cut] for s, d in data.items()}, cfg, FREE)
    pd.testing.assert_series_equal(part.equity, full.equity.loc[:cut], check_freq=False)
