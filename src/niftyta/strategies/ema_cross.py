import pandas as pd
import talib

from ..backtest.strategies import ema_cross_signals
from .base import BLUE, ORANGE, Line, Param, Strategy, config

_I = config("indicators.yaml")


def compute(bars: pd.DataFrame, p: dict) -> pd.DataFrame:
    close = bars["close"].to_numpy(float)
    out = pd.DataFrame(index=bars.index)
    out["ema_fast"] = talib.EMA(close, int(p["fast"]))
    out["ema_slow"] = talib.EMA(close, int(p["slow"]))
    out["entry"], out["exit"] = ema_cross_signals(out["ema_fast"], out["ema_slow"])
    return out


STRATEGY = Strategy(
    key="ema_cross", name="EMA crossover", order=3,
    rules="Buy when the fast EMA crosses above the slow EMA. Sell when it crosses below.",
    params=(Param("fast", "Fast EMA", _I["ema_fast"]["period"], 2, 100),
            Param("slow", "Slow EMA", _I["ema_slow"]["period"], 3, 300)),
    compute=compute,
    overlays=(Line("ema_fast", "Fast EMA", BLUE), Line("ema_slow", "Slow EMA", ORANGE)))
