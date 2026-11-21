from datetime import date

import numpy as np
import pandas as pd
import pytest

from niftyta.data.nse_provider import NSEBhavcopyProvider, parse_bhavcopy
from niftyta.data.provider import COLUMNS, DayProvider
from niftyta.data.service import get_daily, sync_days
from niftyta.data.store import PriceStore
from niftyta.data.validate import symbol_gaps, validate_day

HEADER = ("SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, "
          "CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER")


def bar_row(sym, day, o, h, l, c, v=1000, dq=500, series="EQ"):
    return f" {sym}, {series}, {day:%d-%b-%Y}, {c}, {o}, {h}, {l}, {c}, {c}, {c}, {v}, 1, 1, {dq}, 50"


class FakeDayProvider(DayProvider):
    """Serves a fixed set of trading days; any other weekday is a holiday (None)."""
    name = "fake"

    def __init__(self, days_bars: dict):
        self.days_bars = days_bars
        self.calls = []

    def fetch_day(self, day):
        self.calls.append(day)
        return self.days_bars.get(day)


def make_day(day, symbols=("RELIANCE", "TCS")):
    rows = [{"symbol": s, "date": pd.Timestamp(day), "open": 100.0, "high": 105.0,
             "low": 99.0, "close": 102.0, "adj_close": 102.0, "volume": 1000.0,
             "deliv_qty": 500.0} for s in symbols]
    return pd.DataFrame(rows).set_index("symbol")


def test_parse_bhavcopy_keeps_only_eq(tmp_path):
    f = tmp_path / "b.csv"
    f.write_text("\n".join([HEADER,
                            bar_row("RELIANCE", date(2024, 11, 25), 1290, 1304.45, 1282.45, 1287),
                            bar_row("RELIANCE", date(2024, 11, 25), 1, 1, 1, 1, series="BE")]))
    df = parse_bhavcopy(f)
    assert list(df.index) == ["RELIANCE"]
    assert df.iloc[0]["close"] == 1287 and df.iloc[0]["deliv_qty"] == 500
    assert df.iloc[0]["date"] == pd.Timestamp("2024-11-25")


def test_validate_day_drops_duplicates_and_bad_rows():
    df = make_day("2024-01-02", symbols=("A", "A", "B"))
    df.iloc[2, df.columns.get_loc("high")] = 1.0  # high below close: invalid
    clean, stats = validate_day(df)
    assert stats["duplicates_removed"] == 1 and stats["invalid_dropped"] == 1
    assert list(clean.index) == ["A"]


def test_symbol_gaps_reported_not_filled():
    cal = pd.DatetimeIndex(pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]))
    stock = pd.DatetimeIndex(pd.to_datetime(["2024-01-02", "2024-01-04", "2024-01-05"]))
    assert symbol_gaps(stock, cal) == ["2024-01-03"]


def test_sync_downloads_each_day_once_and_records_holidays(tmp_path):
    store = PriceStore(tmp_path / "t.db")
    days = {date(2024, 1, 2): make_day("2024-01-02"), date(2024, 1, 3): make_day("2024-01-03")}
    p = FakeDayProvider(days)
    rep = sync_days(date(2024, 1, 1), date(2024, 1, 6), store, p)  # Mon..Fri
    assert rep.downloaded_traded == 2 and rep.marked_holiday == 3  # 4th and 5th are holidays here
    assert store.day_status(date(2024, 1, 4)) == "holiday"
    rep2 = sync_days(date(2024, 1, 1), date(2024, 1, 6), store, p)
    assert rep2.already_cached == 5 and rep2.downloaded_traded == 0
    assert len(p.calls) == 5  # no second download of anything
    store.close()


def test_get_daily_returns_symbol_and_gap(tmp_path):
    store = PriceStore(tmp_path / "t.db")
    days = {}
    for d in pd.bdate_range("2024-01-01", "2024-01-12"):
        days[d.date()] = make_day(d, symbols=("RELIANCE",) if d.day != 4 else ("TCS",))
    df, gaps, rep = get_daily("RELIANCE", years=1, end=date(2024, 1, 13),
                              store=store, provider=FakeDayProvider(days))
    assert len(df) == 9  # 10 sessions, RELIANCE absent on the 4th
    assert gaps == ["2024-01-04"]  # reported, not filled
    store.close()


def test_store_upsert_is_idempotent(tmp_path):
    store = PriceStore(tmp_path / "t.db")
    d = make_day("2024-01-02")
    store.upsert_prices(d, "fake")
    store.upsert_prices(d, "fake")
    assert len(store.load("RELIANCE", date(2024, 1, 1), date(2024, 2, 1))) == 1
    store.close()


@pytest.mark.network
def test_live_nse_reliance_five_years(tmp_path):
    store = PriceStore(tmp_path / "live.db")
    df, gaps, rep = get_daily("RELIANCE", years=5, store=store, provider=NSEBhavcopyProvider(raw_dir=tmp_path / "raw", pause_seconds=0.2))
    assert len(df) > 1000
    assert df.index.is_unique and df.index.is_monotonic_increasing
    store.close()


def test_closed_day_serving_previous_session_is_holiday(tmp_path, monkeypatch):
    """NSE serves the previous session's file on a closed day; it must count as no session."""
    f = tmp_path / "sec_bhavdata_full_20220126.csv"
    f.write_text("\n".join([HEADER, bar_row("RELIANCE", date(2022, 1, 25), 1, 2, 1, 2)]))
    p = NSEBhavcopyProvider(raw_dir=tmp_path, pause_seconds=0)
    assert p.fetch_day(date(2022, 1, 26)) is None


def test_parse_historical_layout(tmp_path):
    """Pre-2020 archive layout: OPEN/HIGH/LOW/CLOSE/TOTTRDQTY/TIMESTAMP, no delivery."""
    import zipfile
    csv = ("SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
           "RELIANCE,EQ,1290,1304.45,1282.45,1287,1290.95,1265.4,28923341,1,25-NOV-2024,1,INE002A01018,\n"
           "RELIANCE,BE,1,1,1,1,1,1,1,1,25-NOV-2024,1,INE002A01018,\n")
    z = tmp_path / "cm_hist_20241125.csv.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("cm25NOV2024bhav.csv", csv)
    df = parse_bhavcopy(z)
    assert list(df.index) == ["RELIANCE"]
    assert df.iloc[0]["close"] == 1287 and df.iloc[0]["volume"] == 28923341
    assert pd.isna(df.iloc[0]["deliv_qty"])
