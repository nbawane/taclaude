"""Data-source interface. Each source returns one trading day for all symbols."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd

# Columns of a daily bar. adj_close equals close until corporate-action adjustment is added.
COLUMNS = ["open", "high", "low", "close", "adj_close", "volume", "deliv_qty"]


class DayProvider(ABC):
    name: str

    @abstractmethod
    def fetch_day(self, day: date) -> pd.DataFrame | None:
        """Return all listed-equity bars for `day`, indexed by symbol, with a 'date' column
        and COLUMNS. Return None if no trading session took place that day."""
