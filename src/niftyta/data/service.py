"""Cache-first access. Each trading day is downloaded once and stored; days already
checked are never re-downloaded."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import time

import pandas as pd

from .nse_provider import NSEBhavcopyProvider
from .provider import DayProvider
from .store import PriceStore
from .validate import symbol_gaps, validate_day


@dataclass
class SyncReport:
    weekdays_checked: int = 0
    already_cached: int = 0
    downloaded_traded: int = 0
    marked_holiday: int = 0
    not_yet_published: list[str] = field(default_factory=list)
    rows_dropped: int = 0
    stopped_early: bool = False

    def summary(self) -> str:
        return (f"weekdays {self.weekdays_checked}, cached {self.already_cached}, "
                f"downloaded {self.downloaded_traded}, holidays {self.marked_holiday}, "
                f"rows dropped {self.rows_dropped}, not yet published {len(self.not_yet_published)}"
                + (" (stopped early; rerun to continue)" if self.stopped_early else ""))


def sync_days(start: date, end: date, store: PriceStore, provider: DayProvider,
              budget_seconds: float | None = None) -> SyncReport:
    """Download and store every weekday in [start, end) not yet recorded.
    With budget_seconds, stop after that much time; a later run resumes where it left off."""
    rep = SyncReport()
    today = date.today()
    t0 = time.monotonic()
    for ts in pd.bdate_range(start, end - timedelta(days=1)):
        day = ts.date()
        rep.weekdays_checked += 1
        if store.day_status(day) is not None:
            rep.already_cached += 1
            continue
        if budget_seconds is not None and time.monotonic() - t0 > budget_seconds:
            rep.stopped_early = True
            break
        bars = provider.fetch_day(day)
        if bars is None:
            # Very recent days may simply not be published yet; don't record those as holidays.
            if day >= today - timedelta(days=1):
                rep.not_yet_published.append(day.isoformat())
                continue
            store.set_day_status(day, "holiday")
            rep.marked_holiday += 1
        else:
            clean, stats = validate_day(bars)
            rep.rows_dropped += stats["invalid_dropped"] + stats["duplicates_removed"]
            store.upsert_prices(clean, provider.name)
            store.set_day_status(day, "traded")
            rep.downloaded_traded += 1
    return rep


def get_daily(symbol: str, years: int = 5, end: date | None = None,
              store: PriceStore | None = None, provider: DayProvider | None = None,
              budget_seconds: float | None = None,
              ) -> tuple[pd.DataFrame, list[str], SyncReport]:
    """Validated daily bars for `symbol` over the last `years` years, plus stock-level gaps."""
    own_store = store is None
    store = store or PriceStore()
    provider = provider or NSEBhavcopyProvider()
    end = end or date.today() + timedelta(days=1)  # exclusive
    try:
        start = end.replace(year=end.year - years)
    except ValueError:  # 29 Feb in a non-leap year
        start = end.replace(year=end.year - years, day=28)
    try:
        rep = sync_days(start, end, store, provider, budget_seconds)
        calendar = store.trading_dates(start, end)
        df = store.load(symbol, start, end)
        gaps = symbol_gaps(pd.DatetimeIndex(df.index), calendar)
        return df, gaps, rep
    finally:
        if own_store:
            store.close()
