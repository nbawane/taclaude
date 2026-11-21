"""Indicator calculations. Inputs are closed daily bars; output is aligned to the same dates.
Warm-up rows (before enough history exists) are NaN, never filled."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import talib
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "indicators.yaml"


def load_params(path: Path | str = DEFAULT_CONFIG) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def compute_indicators(df: pd.DataFrame, params: dict | None = None, price: str = "close") -> pd.DataFrame:
    """Return the configured indicators for df[price]. Column names include their period."""
    p = params or load_params()
    close = df[price].to_numpy(dtype="float64")
    out = pd.DataFrame(index=df.index)

    n = p["rsi"]["period"]
    out[f"rsi_{n}"] = talib.RSI(close, timeperiod=n)

    for key in ("ema_fast", "ema_slow"):
        n = p[key]["period"]
        out[f"ema_{n}"] = talib.EMA(close, timeperiod=n)

    for key in ("sma_short", "sma_long"):
        n = p[key]["period"]
        out[f"sma_{n}"] = talib.SMA(close, timeperiod=n)

    b = p["bbands"]
    upper, middle, lower = talib.BBANDS(close, timeperiod=b["period"],
                                        nbdevup=b["std"], nbdevdn=b["std"], matype=0)
    out[f"bb_upper_{b['period']}_{b['std']}"] = upper
    out[f"bb_middle_{b['period']}_{b['std']}"] = middle
    out[f"bb_lower_{b['period']}_{b['std']}"] = lower
    return out
