import numpy as np
import pandas as pd

from niftyta.backtest.mtf_sma import signals, streak


def daily(close):
    idx = pd.bdate_range("2018-01-01", periods=len(close))
    c = pd.Series(close, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "adj_close": c, "volume": 1.0,
                         "deliv_qty": np.nan})


def test_streak_counts_consecutive_true():
    assert list(streak(np.array([True, True, False, True, True, True]))) == [1, 2, 0, 1, 2, 3]


def test_entry_only_on_third_close_above_sma():
    s = signals(daily([10] * 30 + [11, 12, 13, 14, 15]), period=20, confirm_days=3, htf=False)
    assert list(np.flatnonzero(s["entry"])) == [32]


def test_exit_when_close_below_sma():
    s = signals(daily([10] * 30 + [9]), period=20, htf=False)
    assert s["exit"].iloc[-1] and not s["exit"].iloc[-2]


def test_higher_timeframes_do_not_look_ahead():
    rng = np.random.default_rng(1)
    d = daily(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 900))))
    full = signals(d, period=20)
    for cut in (600, 701, 853):
        part = signals(d.iloc[:cut], period=20)
        pd.testing.assert_frame_equal(part, full.iloc[:cut])
