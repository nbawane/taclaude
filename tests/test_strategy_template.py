import numpy as np
import pandas as pd
import pytest

from niftyta.backtest.engine import run_backtest
from niftyta.backtest.portfolio import PortfolioConfig
from niftyta.pipeline import tester
from niftyta.strategies import all_strategies

STRATEGIES = all_strategies()


def raw(seed=3, n=900):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n)))
    opn = close * (1 + rng.normal(0, 0.004, n))
    return pd.DataFrame({"open": opn, "high": np.maximum(opn, close) * 1.01, "low": np.minimum(opn, close) * 0.99,
                         "close": close, "adj_close": close, "volume": 1000.0},
                        index=pd.bdate_range("2019-01-01", periods=n))


def test_all_four_strategies_are_found_in_order():
    assert list(STRATEGIES) == ["sma_mtf", "rsi", "ema_cross", "bbands"]


@pytest.mark.parametrize("key", list(STRATEGIES))
def test_strategy_columns_and_no_look_ahead(key):
    s, data = STRATEGIES[key], raw()
    full = tester.prepare(s, data, s.defaults())
    assert {x.column for x in s.overlays + s.panel} <= set(full.columns)
    assert full["entry"].sum() > 0 and not (full["entry"] & ~full["ready"]).any()
    cut = tester.prepare(s, data.iloc[:700], s.defaults())
    pd.testing.assert_frame_equal(cut, full.iloc[:700], check_dtype=False)


@pytest.mark.parametrize("key", list(STRATEGIES))
def test_default_single_stock_run_matches_original_engine(key):
    s = STRATEGIES[key]
    f = tester.prepare(s, raw(), s.defaults())
    cfg = PortfolioConfig(stop="none", max_positions=1, max_position_pct=1.0)
    result, _ = tester.run({"A": f}, cfg)
    old = run_backtest(f, f["entry"].to_numpy(), f["exit_sma"].to_numpy())
    assert len(result.trades) == len(old.trades)
    if len(old.trades):
        np.testing.assert_allclose(result.trades["exit_price"], old.trades["exit_price"])


def test_buy_and_hold_and_warnings():
    c = pd.Series([100.0, 50.0, 200.0], index=pd.to_datetime(["2020-01-01", "2020-06-01", "2021-01-01"]))
    b = tester.buy_and_hold(c)
    assert b["total_return"] == 1.0 and b["max_drawdown"] == -0.5
    w = tester.warnings({"trades": 3, "cagr": 0.0}, pd.DataFrame([{"period": "x", "cagr": -0.1}]), {"index": b})
    assert len(w) == 3
