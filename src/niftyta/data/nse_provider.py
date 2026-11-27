"""Official NSE daily bhavcopy (end-of-day, unadjusted) from NSE's public archive.

Two archive layouts are used, newest first:
  1. sec_bhavdata_full_DDMMYYYY.csv  (2020 onward; includes delivery quantity)
  2. cmDDMONYYYYbhav.csv.zip         (2016 onward; no delivery quantity)
No login or cookies are used. A closed day (weekend or holiday) has no file of its own:
NSE either returns 404 or serves the previous session's file, which we detect and skip.
"""
from __future__ import annotations

import io
import time
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from .provider import COLUMNS, DayProvider

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "nse_bhavcopy"
EQUITY_SERIES = ["EQ", "BE", "BZ"]  # in order of preference
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}
FULL_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{stamp}.csv"
HIST_URL = "https://nsearchives.nseindia.com/content/historical/EQUITIES/{yyyy}/{mon}/cm{stamp}bhav.csv.zip"


def _read_raw(path: Path) -> pd.DataFrame:
    """Read a raw file whatever it is: CSV, zipped CSV, or zipped Excel."""
    data = path.read_bytes()
    if data[:2] == b"PK":  # zip container
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if any(n.startswith("xl/") for n in zf.namelist()):
                return pd.read_excel(io.BytesIO(data), engine="openpyxl")
            csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            return pd.read_csv(io.BytesIO(zf.read(csv_name)), skipinitialspace=True)
    return pd.read_csv(io.BytesIO(data), skipinitialspace=True)


def parse_bhavcopy(path: Path) -> pd.DataFrame:
    """Parse one day's file (either layout) into equity rows indexed by symbol.
    Keeps EQ plus BE/BZ (trade-to-trade), so a stock moved between them has no gap."""
    raw = _read_raw(path)
    raw.columns = raw.columns.str.strip()
    if "DATE1" in raw.columns:  # newer layout
        date_col, open_c, high_c, low_c, close_c, vol_c = "DATE1", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY"
        deliv = raw.get("DELIV_QTY")
    else:  # historical layout
        date_col, open_c, high_c, low_c, close_c, vol_c = "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"
        deliv = None
    for col in ("SYMBOL", "SERIES", date_col):
        raw[col] = raw[col].astype(str).str.strip()
    eq = raw[raw["SERIES"].isin(EQUITY_SERIES)]
    # one row per symbol; if it appears in several series, EQ wins over BE over BZ
    eq = eq.sort_values("SERIES", key=lambda s: s.map(EQUITY_SERIES.index), kind="stable")
    eq = eq.drop_duplicates("SYMBOL").sort_index()
    num = lambda c: pd.to_numeric(eq[c], errors="coerce").values  # noqa: E731
    out = pd.DataFrame({
        "symbol": eq["SYMBOL"].values,
        "date": pd.to_datetime(eq[date_col], format="%d-%b-%Y").values,
        "open": num(open_c), "high": num(high_c), "low": num(low_c), "close": num(close_c),
        "adj_close": num(close_c), "volume": num(vol_c),
        "deliv_qty": pd.to_numeric(deliv[eq.index], errors="coerce").values if deliv is not None else float("nan"),
    })
    return out.set_index("symbol")[["date"] + COLUMNS]


class NSEBhavcopyProvider(DayProvider):
    name = "nse_bhavcopy"

    def __init__(self, raw_dir: Path = RAW_DIR, pause_seconds: float = 0.5):
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.pause = pause_seconds

    def _download(self, url: str, path: Path) -> bool:
        """Fetch url into path if not cached. Returns False on 404 (no such file)."""
        if path.exists():
            return True
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        path.write_bytes(resp.content)
        time.sleep(self.pause)  # be polite to NSE's servers
        return True

    def fetch_day(self, day: date) -> pd.DataFrame | None:
        sources = [
            (self.raw_dir / f"sec_bhavdata_full_{day:%Y%m%d}.csv",
             FULL_URL.format(stamp=f"{day:%d%m%Y}")),
            (self.raw_dir / f"cm_hist_{day:%Y%m%d}.csv.zip",
             HIST_URL.format(yyyy=f"{day:%Y}", mon=f"{day:%b}".upper(), stamp=f"{day:%d%b%Y}".upper())),
        ]
        for path, url in sources:
            if not self._download(url, path):
                continue
            bars = parse_bhavcopy(path)
            # On closed days NSE serves the previous session's file: check the file's own date.
            if bars.empty or not (bars["date"] == pd.Timestamp(day)).any():
                continue  # stale file in this layout; the other may still have the session
            return bars
        return None  # no layout has this date: no session that day
