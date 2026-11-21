"""DuckDB store: one file (data/niftyta.duckdb) with daily prices and the trading calendar.
DuckDB is open source (MIT), embedded (no server), and columnar, so multi-stock queries are fast."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from .provider import COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = PROJECT_ROOT / "data" / "niftyta.duckdb"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS prices_daily (
    symbol    VARCHAR NOT NULL,
    date      DATE NOT NULL,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    adj_close DOUBLE,
    volume    DOUBLE,
    deliv_qty DOUBLE,
    source    VARCHAR NOT NULL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS index_daily (
    index_name VARCHAR NOT NULL,
    date       DATE NOT NULL,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    volume DOUBLE, turnover_cr DOUBLE,
    PRIMARY KEY (index_name, date)
);
CREATE TABLE IF NOT EXISTS trading_days (
    date       DATE PRIMARY KEY,        -- every weekday we have checked
    status     VARCHAR NOT NULL,        -- 'traded' or 'holiday'
    fetched_at TIMESTAMP NOT NULL       -- UTC
);
"""


class PriceStore:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.path))
        self.conn.execute(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- trading calendar -------------------------------------------------
    def day_status(self, day: date) -> str | None:
        row = self.conn.execute("SELECT status FROM trading_days WHERE date = ?", [day]).fetchone()
        return row[0] if row else None

    def set_day_status(self, day: date, status: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO trading_days VALUES (?, ?, ?)",
                          [day, status, datetime.now(timezone.utc).replace(tzinfo=None)])

    def trading_dates(self, start: date, end: date) -> pd.DatetimeIndex:
        rows = self.conn.execute(
            "SELECT date FROM trading_days WHERE status = 'traded' AND date >= ? AND date < ? ORDER BY date",
            [start, end]).fetchall()
        return pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows]), name="date")

    # --- prices -----------------------------------------------------------
    def upsert_prices(self, df: pd.DataFrame, source: str) -> int:
        """df indexed by symbol with a 'date' column and COLUMNS. Re-inserts overwrite."""
        if df.empty:
            return 0
        frame = df.reset_index()[["symbol", "date"] + COLUMNS].copy()
        frame["source"] = source
        self.conn.register("incoming", frame)
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO prices_daily "
                "SELECT symbol, CAST(date AS DATE), open, high, low, close, adj_close, volume, deliv_qty, source "
                "FROM incoming")
        finally:
            self.conn.unregister("incoming")
        return len(frame)

    def load(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        cols = ", ".join(COLUMNS)
        df = self.conn.execute(
            f"SELECT date, {cols} FROM prices_daily WHERE symbol = ? AND date >= ? AND date < ? ORDER BY date",
            [symbol, start, end]).df()
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")

    def upsert_index(self, df: pd.DataFrame) -> int:
        """df with index_name, date and OHLC/volume columns (one row per index per day)."""
        if df.empty:
            return 0
        cols = ["index_name", "date", "open", "high", "low", "close", "volume", "turnover_cr"]
        self.conn.register("incoming_idx", df[cols])
        try:
            self.conn.execute("INSERT OR REPLACE INTO index_daily SELECT index_name, CAST(date AS DATE), "
                              "open, high, low, close, volume, turnover_cr FROM incoming_idx")
        finally:
            self.conn.unregister("incoming_idx")
        return len(df)

    def load_index(self, index_name: str, start: date, end: date) -> pd.DataFrame:
        df = self.conn.execute(
            "SELECT date, open, high, low, close, volume, turnover_cr FROM index_daily "
            "WHERE index_name = ? AND date >= ? AND date < ? ORDER BY date",
            [index_name, start, end]).df()
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")

    def load_many(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        """Long-format bars for several symbols: columns symbol + COLUMNS, indexed by date."""
        cols = ", ".join(COLUMNS)
        df = self.conn.execute(
            f"SELECT symbol, date, {cols} FROM prices_daily WHERE symbol IN (SELECT UNNEST(?)) "
            "AND date >= ? AND date < ? ORDER BY symbol, date",
            [symbols, start, end]).df()
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")
