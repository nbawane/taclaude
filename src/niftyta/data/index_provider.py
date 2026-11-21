"""Daily index closes from NSE's public archive (ind_close_all_DDMMYYYY.csv).
One file per trading day holds every NSE index. Like the stock files, a closed day
has no file of its own, or the file carries the previous session's date."""
from __future__ import annotations

import io
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from .nse_provider import HEADERS, PROJECT_ROOT

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "nse_indices"
URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{stamp}.csv"
INDEX_COLUMNS = {"Index Name": "index_name", "Index Date": "date", "Open Index Value": "open",
                 "High Index Value": "high", "Low Index Value": "low",
                 "Closing Index Value": "close", "Volume": "volume",
                 "Turnover (Rs. Cr.)": "turnover_cr"}


def parse_index_file(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    raw.columns = raw.columns.str.strip()
    df = raw[list(INDEX_COLUMNS)].rename(columns=INDEX_COLUMNS)
    df["index_name"] = df["index_name"].astype(str).str.strip()
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y")
    for c in ("open", "high", "low", "close", "volume", "turnover_cr"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def fetch_index_day(day: date, raw_dir: Path = RAW_DIR, pause: float = 0.5) -> pd.DataFrame | None:
    """All index rows for `day`, or None if no session that day."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"ind_close_all_{day:%Y%m%d}.csv"
    if not path.exists():
        resp = requests.get(URL.format(stamp=f"{day:%d%m%Y}"), headers=HEADERS, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        path.write_bytes(resp.content)
        time.sleep(pause)
    # A few archive files stamp the date month-first (e.g. "04-06-2023" for 6 April 2023), so
    # accept either order. A closed day's file carries the previous session's date, which
    # matches neither form for the requested day.
    raw = pd.read_csv(path, usecols=lambda c: c.strip() == "Index Date")
    stamps = set(raw.iloc[:, 0].astype(str).str.strip())
    if not stamps & {f"{day:%d-%m-%Y}", f"{day:%m-%d-%Y}"}:
        return None
    df = parse_index_file(path)
    df["date"] = pd.Timestamp(day)  # the file belongs to this session
    return df
