import pandas as pd

from niftyta.backtest.strategies import sma_cross_signals


def test_sma_cross_signals_fire_only_on_the_cross_bar():
    close = pd.Series([10, 10, 10, 9, 12, 13, 8, 7], dtype=float)
    entry, exit_ = sma_cross_signals(close, 3)
    assert entry.nonzero()[0].tolist() == [4]
    assert exit_.nonzero()[0].tolist() == [3, 6]


def test_sma_cross_signals_no_lookahead():
    close = pd.Series([10, 11, 9, 12, 13, 8, 7, 14, 15, 6], dtype=float)
    full = sma_cross_signals(close, 3)
    part = sma_cross_signals(close[:6], 3)
    for f, p in zip(full, part):
        assert (f[:6] == p).all()
