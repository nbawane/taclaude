import numpy as np
import pandas as pd
import pytest
import yaml

from niftyta.backtest.gfs import (closed_bars, divergence_at, last_closed_value, pivot_lows,
                                  rsi_series, simulate)

CFG = yaml.safe_load(open(__import__("pathlib").Path(__file__).resolve().parents[1] / "config" / "strategies.yaml"))["gfs"]
ZERO = {"brokerage_per_order_inr": 0, "exchange_txn_charge": 0, "sebi_fee": 0, "gst_rate": 0,
        "stamp_duty_buy": 0, "stt_delivery": 0, "slippage_per_side": 0}


def daily(rows):
    """rows: list of (open, high, low, close). Business days from 2024-01-01."""
    idx = pd.bdate_range("2024-01-01", periods=len(rows))
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["adj_close"] = df["close"]; df["volume"] = 1000.0; df["deliv_qty"] = 500.0
    return df


def flat(n, o=100, h=101, l=99, c=100.5):
    return [(o, h, l, c)] * n


def trig(n, at):
    t = np.zeros(n, bool); t[at] = True
    return t


def test_buy_stop_fills_at_alert_high_and_target_is_2_5R():
    rows = flat(3) + [(100, 102, 99.5, 101.5)] + [(101, 107, 101, 106)] + flat(3)
    df = daily(rows)
    r = simulate(df, trig(len(df), 2), CFG, "A", costs=ZERO, initial_cash=10_000)
    t = r.trades.iloc[0]
    assert t["entry_price"] == pytest.approx(101.0)          # alert high 101
    assert t["exit_price"] == pytest.approx(106.0)            # 101 + 2.5 * (101 - 99)
    assert t["R"] == pytest.approx(2.5)


def test_alert_cancelled_when_alert_low_breached_first():
    rows = flat(3) + [(100, 100, 98.5, 99)] + [(100, 105, 100, 104)] + flat(3)
    df = daily(rows)
    r = simulate(df, trig(len(df), 2), CFG, "A", costs=ZERO)
    assert len(r.trades) == 0 and not r.open_at_end


def test_alert_expires_after_two_bars():
    rows = flat(3) + [(100, 100, 100, 100)] * 2 + [(100, 105, 100, 104)] + flat(3)
    df = daily(rows)  # bars 3 and 4 never reach 101; bar 5 would, but the order has expired
    r = simulate(df, trig(len(df), 2), CFG, "A", costs=ZERO)
    assert len(r.trades) == 0 and not r.open_at_end


def test_gap_above_stop_fills_at_open():
    rows = flat(3) + [(103, 104, 102.5, 103.5)] + [(103.5, 104, 103, 103.8)] + flat(2)
    df = daily(rows)
    r = simulate(df, trig(len(df), 2), CFG, "A", costs=ZERO)
    assert r.trades.iloc[0]["entry_price"] == pytest.approx(103.0)   # filled at the gapped open, not at 101
    assert r.trades.iloc[0]["entry_date"] == df.index[3]


def test_stop_loss_is_alert_low():
    rows = flat(3) + [(100, 102, 99.5, 101.5)] + [(101, 101, 98, 98.5)] + flat(3)
    df = daily(rows)
    r = simulate(df, trig(len(df), 2), CFG, "A", costs=ZERO)
    t = r.trades.iloc[0]
    assert t["exit_price"] == pytest.approx(99.0)            # stopped at alert low
    assert t["R"] == pytest.approx(-1.0)


def test_mode_b_scale_out_then_rest_exit_on_rsi_below_55():
    up = [(100 + i * 0.5 - 0.2, 100 + i * 0.5 + 0.3, 100 + i * 0.5 - 0.4, 100 + i * 0.5) for i in range(30)]
    down = [(115 - i * 2 + 0.2, 115 - i * 2 + 0.3, 115 - i * 2 - 0.4, 115 - i * 2) for i in range(1, 21)]
    df = daily(up + down)
    r = simulate(df, trig(len(df), 25), CFG, "B", costs=ZERO)
    assert len(r.trades) == 1
    assert "scale-out 50%" in r.trades.iloc[0]["reason"]


def test_pivot_low_is_confirmed_only_after_n_bars():
    low = np.array([10, 9, 8, 9, 10, 11, 12], float)  # strict minimum at index 2
    piv = pivot_lows(low, 2)
    assert piv[2] and piv.sum() == 1
    rsi = np.full(len(low), 40.0)
    # at bar 3 the pivot at 2 is NOT yet confirmed (needs bar 4)
    assert divergence_at(3, low, rsi, piv, dict(CFG, divergence_recent=5, divergence_min_gap=0,
                                              divergence_max_gap=30)) is False


def test_htf_value_uses_only_bars_closed_before_the_son_date():
    labels = pd.DatetimeIndex(pd.to_datetime(["2024-01-05", "2024-01-12"]))  # weekly (Fridays)
    htf = pd.Series([70.0, 80.0], index=labels)
    son = pd.DatetimeIndex(pd.to_datetime(["2024-01-05", "2024-01-08", "2024-01-12", "2024-01-15"]))
    v = last_closed_value(htf, son)
    assert np.isnan(v[0])        # on the week's own Friday the week is not yet usable
    assert v[1] == 70.0          # Monday: the week ending 5 Jan is closed
    assert v[2] == 70.0          # Friday 12 Jan: 12 Jan bar not usable yet
    assert v[3] == 80.0          # Monday after: 12 Jan bar is closed


def test_no_lookahead_in_htf_rsi_truncation():
    rng = np.random.default_rng(3)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 600)))
    idx = pd.bdate_range("2020-01-01", periods=600)
    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                       "adj_close": close, "volume": 1.0, "deliv_qty": 1.0}, index=idx)
    cut = 400
    full = last_closed_value(rsi_series(closed_bars(df, "1W"), 14), closed_bars(df, "1D").index[:cut])
    part = last_closed_value(rsi_series(closed_bars(df.iloc[:cut], "1W"), 14), closed_bars(df.iloc[:cut], "1D").index)
    np.testing.assert_allclose(full[:cut - 10], part[:cut - 10], equal_nan=True)


def test_simulate_uses_the_rsi_it_is_given_for_mode_b_exits():
    """On a slice, the caller passes full-history RSI; the simulator must use it, not recompute."""
    rows = flat(3) + [(100, 102, 99.5, 101.5)] + [(102.5, 104, 102, 103)] * 8  # lows stay above break-even (101)
    df = daily(rows)
    rsi = np.full(len(df), 50.0)
    rsi[4] = 65.0            # closes at/above 60 -> sell 50% at the next open, stop to break-even
    rsi[6] = 50.0            # closes below 55 -> sell the rest at the next open
    r = simulate(df, trig(len(df), 2), CFG, "B", costs=ZERO, rsi=rsi)
    reason = r.trades.iloc[0]["reason"]
    assert "scale-out 50%" in reason and "RSI below 55" in reason
