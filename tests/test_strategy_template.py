import numpy as np
import pandas as pd
import pytest

from niftyta.backtest.engine import run_backtest
from niftyta.backtest.gfs import simulate
from niftyta.backtest.portfolio import PortfolioConfig
from niftyta.pipeline import tester
from niftyta.reporting import mtf_chart, rsi_guides
from niftyta.strategies import all_strategies
from niftyta.strategies.base import config

STRATEGIES = all_strategies()


def raw(seed=3, n=900):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n)))
    opn = close * (1 + rng.normal(0, 0.004, n))
    return pd.DataFrame({"open": opn, "high": np.maximum(opn, close) * 1.01, "low": np.minimum(opn, close) * 0.99,
                         "close": close, "adj_close": close, "volume": 1000.0},
                        index=pd.bdate_range("2019-01-01", periods=n))


def test_all_strategies_are_found_in_order():
    assert list(STRATEGIES) == ["sma_mtf", "rsi", "ema_cross", "bbands", "gfs"]


@pytest.mark.parametrize("key", list(STRATEGIES))
def test_strategy_columns_and_no_look_ahead(key):
    s, data = STRATEGIES[key], raw()
    full = tester.prepare(s, data, s.defaults())
    assert {x.column for x in s.overlays + s.panel} <= set(full.columns)
    assert (key == "gfs" or full["entry"].sum() > 0) and not (full["entry"] & ~full["ready"]).any()
    cut = tester.prepare(s, data.iloc[:700], s.defaults())
    pd.testing.assert_frame_equal(cut, full.iloc[:700], check_dtype=False)


@pytest.mark.parametrize("key", [k for k, s in STRATEGIES.items() if s.execute is None])
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


@pytest.mark.parametrize("exit_mode", ["A", "B"])
def test_gfs_in_the_tester_matches_its_own_simulator(exit_mode):
    s = STRATEGIES["gfs"]
    params = {**s.defaults(), "exit_mode": exit_mode, "htf_rsi_min": 50, "pullback_high": 55}
    f = tester.prepare(s, raw(n=1500), params)
    f_all = f.loc[f.index[f["ready"]][0]:]
    result, m = tester.run({"A": f}, PortfolioConfig(), f_all.index[0], None, s, params)
    direct = simulate(f_all, f_all["entry"].to_numpy(bool), {**config()["gfs"], **params}, exit_mode,
                      rsi=f_all["rsi_day"].to_numpy())
    assert len(result.trades) == len(direct.trades) > 0 and m["trades"] == len(direct.trades)
    np.testing.assert_allclose(result.equity, direct.equity)
    with pytest.raises(ValueError):
        tester.run({"A": f, "B": f}, PortfolioConfig(), None, None, s, params)


@pytest.mark.parametrize("key", ["gfs", "sma_mtf"])
def test_higher_timeframe_charts_show_the_values_the_rules_use(key):
    s = STRATEGIES[key]
    f = tester.prepare(s, raw(n=1500), s.defaults())
    for tf in s.timeframes:
        view = tester.timeframe_view(f, tf, s.defaults())
        for label, value in view[tf.column].dropna().iloc[-5:-1].items():
            nxt = f.index[f.index > label][0]          # first day the completed candle is used
            assert f.loc[nxt, tf.column] == pytest.approx(value)


@pytest.mark.parametrize("key", ["gfs", "sma_mtf"])
def test_multi_timeframe_chart_has_one_pane_per_timeframe(key):
    s = STRATEGIES[key]
    f = tester.prepare(s, raw(n=1500), s.defaults())
    trades = pd.DataFrame({"entry_date": [f.index[900]], "exit_date": [f.index[910]], "return": [0.01],
                           "stop": [float("-inf")], "target": [float("nan")]})
    panes = mtf_chart.chart_data(s, f, s.defaults(), trades, levels=True)
    assert [p["title"] for p in panes] == ["Monthly", "Weekly", "Daily"]
    for p in panes:
        times = [c["time"] for c in p["candles"]]
        assert times == sorted(set(times))
        assert all([x["time"] for x in line["data"]] == times for line in p["overlays"] + p["panel"])
    assert [m["shape"] for m in panes[-1]["markers"]] == ["arrowUp", "arrowDown"] and not panes[-1]["levels"]
    assert not panes[0]["markers"] and "/*DATA*/" not in mtf_chart.html(panes)
    assert '"layout": "horizontal"' in mtf_chart.html(panes, layout="horizontal")
    assert mtf_chart.height(panes, "horizontal") < mtf_chart.height(panes)
    with pytest.raises(ValueError):
        mtf_chart.html(panes, layout="diagonal")


def test_only_rsi_charts_carry_the_rsi_guides():
    for key, expected in (("gfs", [True] * 3), ("sma_mtf", [False] * 3)):
        s = STRATEGIES[key]
        f = tester.prepare(s, raw(n=1500), s.defaults())
        panes = mtf_chart.chart_data(s, f, s.defaults(), pd.DataFrame())
        assert [p["rsi"] for p in panes] == expected
    assert STRATEGIES["rsi"].rsi_panel and not STRATEGIES["ema_cross"].rsi_panel
    assert sorted(g["level"] for g in (rsi_guides.BAND, *rsi_guides.LINES)) == [20, 40, 60, 80]


def test_chart_shows_the_forming_month_without_changing_completed_values():
    s = STRATEGIES["gfs"]
    f = tester.prepare(s, raw(n=1500), s.defaults())
    f = f.loc[:f.index[(f.index.day > 10) & (f.index.day < 20)][-1]]     # data stops mid-month
    month = s.timeframes[0]
    shown = tester.timeframe_view(f, month, s.defaults(), include_forming=True)
    done = tester.timeframe_view(f, month, s.defaults())
    assert shown["forming"].iloc[-1] and not shown["forming"].iloc[:-1].any()
    assert shown["close"].iloc[-1] == f["close"].iloc[-1] and len(shown) == len(done) + 1
    pd.testing.assert_series_equal(shown[month.column].iloc[:-1], done[month.column], check_freq=False)
    pane = mtf_chart.chart_data(s, f, s.defaults(), pd.DataFrame())[0]
    assert pane["forming"]["time"] == pane["candles"][-1]["time"] and "color" in pane["candles"][-1]
