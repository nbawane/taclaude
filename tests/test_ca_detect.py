import numpy as np
import pandas as pd

from niftyta.data.ca_detect import find_candidates, nearest_clean_factor


def series(closes, vols=None, symbol="X"):
    n = len(closes)
    return pd.DataFrame({"symbol": symbol, "date": pd.bdate_range("2024-01-01", periods=n),
                         "close": closes, "volume": vols if vols is not None else [1000.0] * n})


def test_one_for_one_bonus_is_found():
    closes = [100.0] * 25 + [50.5] + [51.0] * 5
    vols = [1000.0] * 25 + [2100.0] + [1000.0] * 5
    c = find_candidates(series(closes, vols))
    assert len(c) == 1 and c.iloc[0]["suggested_factor"] == 0.5 and c.iloc[0]["confidence"] == "high"


def test_ordinary_crash_and_rally_are_not_candidates():
    closes = [100.0] * 25 + [78.0] + [100.0] * 4 + [130.0]   # -22% day, then a +30% day
    assert find_candidates(series(closes)).empty


def test_clean_ratio_without_volume_jump_is_only_medium():
    closes = [100.0] * 25 + [50.0] + [50.0] * 3
    c = find_candidates(series(closes))   # volume flat
    assert c.iloc[0]["confidence"].startswith("medium")


def test_nearest_clean_factor():
    f, desc, err = nearest_clean_factor(0.1052)
    assert f == 0.1 and err < 0.06
