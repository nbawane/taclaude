import pandas as pd
import pytest

from niftyta.data.corporate_actions import adjust_bars


def bars():
    idx = pd.to_datetime(["2024-10-01", "2024-10-02", "2024-10-03"])
    return pd.DataFrame({"open": [100.0, 100, 50], "high": [101.0, 101, 51], "low": [99.0, 99, 49],
                         "close": [100.0, 100, 50], "adj_close": [100.0, 100, 50],
                         "volume": [1000.0, 1000, 2000]}, index=pd.DatetimeIndex(idx, name="date"))


def test_one_for_one_bonus_halves_history_before_ex_date():
    acts = pd.DataFrame({"symbol": ["RELIANCE"], "ex_date": [pd.Timestamp("2024-10-03")], "factor": [0.5]})
    out, n = adjust_bars(bars(), acts, "RELIANCE")
    assert n == 1
    assert out["close"].tolist() == [50.0, 50.0, 50.0]   # continuous now
    assert out["volume"].tolist() == [2000.0, 2000.0, 2000.0]


def test_other_symbols_and_no_file_unchanged():
    acts = pd.DataFrame({"symbol": ["TCS"], "ex_date": [pd.Timestamp("2024-10-03")], "factor": [0.5]})
    out, n = adjust_bars(bars(), acts, "RELIANCE")
    assert n == 0 and out["close"].tolist() == [100.0, 100.0, 50.0]
    out2, n2 = adjust_bars(bars(), None, "RELIANCE")
    assert n2 == 0
