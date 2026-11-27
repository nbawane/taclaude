import pandas as pd
import talib

from ..backtest.strategies import bbands_signals
from .base import GREY, Line, Param, Strategy, config

_I = config("indicators.yaml")["bbands"]


def compute(bars: pd.DataFrame, p: dict) -> pd.DataFrame:
    close = bars["close"]
    out = pd.DataFrame(index=bars.index)
    out["upper"], out["middle"], out["lower"] = talib.BBANDS(
        close.to_numpy(float), timeperiod=int(p["period"]), nbdevup=p["std"], nbdevdn=p["std"], matype=0)
    out["entry"], out["exit"] = bbands_signals(close, out["lower"], out["upper"])
    return out


STRATEGY = Strategy(
    key="bbands", name="Bollinger Bands", order=4,
    rules="Buy when the close moves back above the lower band. Sell when it moves back below the upper band.",
    params=(Param("period", "Length", _I["period"], 2, 200), Param("std", "Standard deviations", float(_I["std"]), 0.5, 5.0)),
    compute=compute,
    overlays=(Line("upper", "Upper band", GREY), Line("middle", "Middle band", GREY), Line("lower", "Lower band", GREY)))
