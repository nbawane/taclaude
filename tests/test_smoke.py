def test_imports():
    import pandas, numpy, yfinance, matplotlib, yaml  # noqa: F401
    import talib  # noqa: F401
    import vectorbt  # noqa: F401


def test_tiny_vectorbt_backtest():
    import numpy as np
    import pandas as pd
    import vectorbt as vbt

    price = pd.Series(np.linspace(100, 110, 20))
    entries = pd.Series(False, index=price.index)
    exits = pd.Series(False, index=price.index)
    entries.iloc[2] = True
    exits.iloc[10] = True
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=10_000)
    assert pf.trades.count() == 1
    assert pf.total_return() > 0
