import numpy as np
import pandas as pd

from niftyta.pipeline.mtf_sma_run import open_entry
from lightweight_charts.widgets import StaticLWC
from niftyta.reporting.lw_chart import chart_frame, trade_markers


def test_open_entry_is_next_open_after_signal_following_last_exit():
    idx = pd.bdate_range("2024-01-01", periods=8)
    df = pd.DataFrame({"open": np.arange(8.0)}, index=idx)
    entries = np.array([True, False, False, True, False, True, False, False])
    trades = pd.DataFrame({"exit_date": [idx[3]]})
    assert open_entry(df, entries, trades) == (idx[4], 4.0)


def test_trade_markers_are_in_time_order_with_open_position_last():
    d = pd.bdate_range("2024-01-01", periods=6)
    trades = pd.DataFrame({"entry_date": [d[2], d[0]], "exit_date": [d[3], d[1]], "return": [0.05, -0.02]})
    marks = trade_markers(trades, (d[5], 10.0))
    assert [m["time"] for m in marks] == [d[0], d[1], d[2], d[3], d[5]]
    assert marks[1]["text"] == "-2.0%" and marks[-1]["text"] == "open"


def test_chart_receives_real_dates_even_from_microsecond_data():
    d = pd.DataFrame({"close": [1.0, 2.0]}, index=pd.DatetimeIndex(["2024-01-01", "2024-01-02"]).as_unit("us"))
    out = StaticLWC()._df_datetime_format(chart_frame(d))
    assert list(out["time"]) == [1704067200, 1704153600]
