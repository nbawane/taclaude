import numpy as np
import pandas as pd
import pytest

from niftyta.data.timeframes import resample_ohlcv


def daily(dates, opens, highs, lows, closes, vols):
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes,
                         "adj_close": closes, "volume": vols, "deliv_qty": vols},
                        index=pd.DatetimeIndex(pd.to_datetime(dates), name="date"))


def test_weekly_bar_ohlcv_is_correct():
    # Week of 2 Jan 2024 (Tue-Fri); next week starts Mon 8 Jan.
    d = daily(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"],
              [10, 11, 12, 13, 20], [15, 16, 17, 14, 21], [9, 8, 10, 12, 19],
              [11, 12, 13, 13.5, 20.5], [100, 200, 300, 400, 500])
    w = resample_ohlcv(d, "1W", as_of=pd.Timestamp("2024-01-09").date())
    first = w.iloc[0]
    assert first["open"] == 10 and first["high"] == 17 and first["low"] == 8
    assert first["close"] == 13.5 and first["volume"] == 1000
    assert w.index[0] == pd.Timestamp("2024-01-05")  # labelled by Friday
    assert bool(w["partial"].iloc[-1]) is True       # latest week (Mon only) still forming
    assert bool(w["partial"].iloc[0]) is False


def test_monthly_bar_and_partial_flag():
    rows = pd.bdate_range("2024-01-01", "2024-02-29")
    d = daily(rows, np.arange(len(rows)) + 100.0, np.arange(len(rows)) + 105.0,
              np.arange(len(rows)) + 95.0, np.arange(len(rows)) + 101.0, np.ones(len(rows)))
    m = resample_ohlcv(d, "1M", as_of=pd.Timestamp("2024-03-05").date())
    assert len(m) == 2
    assert m.index[0] == pd.Timestamp("2024-01-31")
    assert m.iloc[0]["volume"] == pd.Series(np.ones(len(rows)))[rows.month == 1].sum()
    assert m["partial"].tolist() == [False, False]  # Feb data runs to 29 Feb = month end


def test_no_future_data_leaks_into_earlier_bars():
    rows = pd.bdate_range("2024-01-01", "2024-03-29")
    close = np.linspace(100, 200, len(rows))
    d = daily(rows, close, close + 1, close - 1, close, np.ones(len(rows)))
    full = resample_ohlcv(d, "1W")
    cut = resample_ohlcv(d.loc[:"2024-02-15"], "1W")
    common = cut.index[:-1]  # the last cut bar is partial by construction
    pd.testing.assert_frame_equal(full.loc[common, ["open", "high", "low", "close"]],
                                  cut.loc[common, ["open", "high", "low", "close"]])


def test_bad_timeframe_rejected():
    with pytest.raises(ValueError):
        resample_ohlcv(daily(["2024-01-02"], [1], [1], [1], [1], [1]), "1Y")


def test_blank_delivery_quantity_stays_blank_not_zero():
    d = daily(["2024-01-02", "2024-01-03"], [1, 1], [2, 2], [1, 1], [1.5, 1.5], [10, 10])
    d["deliv_qty"] = np.nan
    w = resample_ohlcv(d, "1W")
    assert w["deliv_qty"].isna().all()           # unknown stays unknown
    d2 = d.copy(); d2.iloc[0, d2.columns.get_loc("deliv_qty")] = 5.0
    assert resample_ohlcv(d2, "1W")["deliv_qty"].iloc[0] == 5.0   # partial knowledge is summed


def test_week_with_holiday_friday_is_complete_once_the_week_has_passed():
    # Mon-Thu traded; Friday 26 Jan 2024 was closed. Evaluated on the following Monday.
    d = daily(["2024-01-22", "2024-01-23", "2024-01-24", "2024-01-25"], [1] * 4, [2] * 4, [1] * 4, [1.5] * 4, [10] * 4)
    assert bool(resample_ohlcv(d, "1W", as_of=pd.Timestamp("2024-01-29").date())["partial"].iloc[-1]) is False
    # ...but on Thursday evening itself the week has not ended yet
    assert bool(resample_ohlcv(d, "1W", as_of=pd.Timestamp("2024-01-25").date())["partial"].iloc[-1]) is True


def test_stale_data_is_flagged_partial():
    d = daily(["2024-01-22", "2024-01-23"], [1] * 2, [2] * 2, [1] * 2, [1.5] * 2, [10] * 2)
    # data stops on Tuesday but the week ended three or more days later: missing sessions, not a holiday
    assert bool(resample_ohlcv(d, "1W", as_of=pd.Timestamp("2024-02-05").date())["partial"].iloc[-1]) is True
