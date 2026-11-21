from niftyta.nl.parse import parse_prompt

KNOWN = {"RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN", "ICICIBANK"}


def test_readme_full_prompt():
    r = parse_prompt("Analyze RELIANCE on the daily timeframe. Apply RSI 14, EMA 9/21 and Bollinger Bands. "
                     "Backtest all three strategies for five years. Compare performance. "
                     "Generate a Pine Script for the best strategy.", KNOWN)
    assert r.symbols == ["RELIANCE"] and r.timeframes == ["1D"]
    assert set(r.strategies) == {"rsi", "ema_cross", "bbands"}
    assert r.years == 5 and r.pine


def test_multiframe_and_single_strategy():
    r = parse_prompt("Test the EMA crossover strategy on daily, weekly and monthly timeframes for TCS", KNOWN)
    assert r.symbols == ["TCS"] and r.strategies == ["ema_cross"]
    assert r.timeframes == ["1D", "1W", "1M"]


def test_unsupported_indicator_is_reported_not_guessed():
    r = parse_prompt("Compare RSI, MACD and Bollinger Band strategies on INFY", KNOWN)
    assert r.symbols == ["INFY"] and "MACD" in r.unsupported
    assert set(r.strategies) == {"rsi", "bbands"}


def test_index_name_expands_to_constituents():
    r = parse_prompt("Find the best-performing strategy among the Nifty 50 stocks, weekly", KNOWN)
    assert len(r.symbols) == 50 and r.timeframes == ["1W"]


def test_unknown_stock_is_flagged():
    r = parse_prompt("Backtest XYZQ", KNOWN)
    assert r.symbols == [] and r.notes
