"""Index constituents from the official NSE lists saved in data/reference/."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
INDEX_FILES = {"NIFTY50": "ind_nifty50list.csv", "BANKNIFTY": "ind_niftybanklist.csv"}


def index_symbols(index: str) -> list[str]:
    df = pd.read_csv(REFERENCE_DIR / INDEX_FILES[index.upper()])
    return sorted(df["Symbol"].str.strip().unique())


def universe(indices=("NIFTY50", "BANKNIFTY")) -> list[str]:
    """Union of the given indices' constituents (today's lists, see survivorship note)."""
    return sorted({s for idx in indices for s in index_symbols(idx)})
