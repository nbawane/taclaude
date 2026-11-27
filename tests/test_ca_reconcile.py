import pandas as pd

from niftyta.data.ca_reconcile import judge

IDX = pd.bdate_range("2024-01-01", periods=60)
EX = IDX[30]


def series(before, after):
    return pd.Series([before] * 30 + [after] * 30, index=IDX, dtype=float)


def test_split_seen_in_both_sources_is_verified_on_the_nse_date():
    out = judge(series(1000, 101), series(100, 101), EX + pd.Timedelta(days=2), 0.1)
    assert out["status"] == "verified" and out["ex_date"] == EX


def test_event_absent_from_nse_prices_is_rejected():
    assert judge(series(100, 100), series(100, 100), EX, 0.5)["status"] == "no_evidence"


def test_jump_without_matching_step_needs_a_check():
    # NSE halves but the other source halves too: it did not adjust, so the two disagree
    assert judge(series(100, 50), series(100, 50), EX, 0.5)["status"] == "check"


def test_combined_event_takes_the_total_factor_from_prices():
    # only a 2:1 split is listed, but both price series show a total of 4:1
    out = judge(series(400, 98), series(100, 98), EX, 0.5)
    assert out["status"] == "verified_combined" and out["factor"] == 0.25 and out["ex_date"] == EX


def test_small_bonus_confirmed_by_step():
    assert judge(series(110, 100), series(100, 100), EX, 10 / 11)["status"] == "verified"


def test_date_before_data_is_outside():
    assert judge(series(100, 50), None, pd.Timestamp("2010-01-01"), 0.5)["status"] == "outside_data"
