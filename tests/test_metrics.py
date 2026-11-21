import numpy as np
import pandas as pd
import pytest

from niftyta.backtest.metrics import performance


def eq(values):
    return pd.Series(values, index=pd.bdate_range("2020-01-01", periods=len(values)), dtype=float)


EMPTY = pd.DataFrame({"pnl": []})


def test_doubling_in_one_year_daily():
    e = eq(np.linspace(100, 200, 252))  # 252 bars = one year at daily frequency
    m = performance(e, EMPTY, 1.0, periods_per_year=252)
    assert m["total_return"] == pytest.approx(1.0)
    assert m["cagr"] == pytest.approx(1.0, rel=1e-3)


def test_same_series_weekly_has_lower_cagr_than_daily_assumption():
    e = eq(np.linspace(100, 200, 52))  # one year of weekly bars
    assert performance(e, EMPTY, 1.0, periods_per_year=52)["cagr"] == pytest.approx(1.0, rel=1e-3)
    assert performance(e, EMPTY, 1.0, periods_per_year=252)["cagr"] != pytest.approx(1.0, rel=1e-3)


def test_max_drawdown_known_value():
    m = performance(eq([100, 120, 90, 110]), EMPTY, 1.0)
    assert m["max_drawdown"] == pytest.approx(90 / 120 - 1)


def test_profit_factor_and_win_rate():
    trades = pd.DataFrame({"pnl": [10, -5, 20, -10]})
    m = performance(eq([100, 110, 105, 125, 115]), trades, 0.5)
    assert m["win_rate"] == pytest.approx(0.5)
    assert m["profit_factor"] == pytest.approx(30 / 15)
    assert m["trades"] == 4
