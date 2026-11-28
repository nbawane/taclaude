import pandas as pd
import talib

from ..backtest.strategies import rsi_signals
from .base import PURPLE, Line, Param, Strategy, config

_S, _I = config()["rsi"], config("indicators.yaml")["rsi"]


def compute(bars: pd.DataFrame, p: dict) -> pd.DataFrame:
    out = pd.DataFrame(index=bars.index)
    out["rsi"] = talib.RSI(bars["close"].to_numpy(float), int(p["period"]))
    out["entry"], out["exit"] = rsi_signals(out["rsi"], p["buy_level"], p["sell_level"])
    out["buy_level"], out["sell_level"] = float(p["buy_level"]), float(p["sell_level"])
    return out


STRATEGY = Strategy(
    key="rsi", name="RSI", order=2,
    rules="Buy when RSI crosses above the buy level. Sell when RSI crosses below the sell level.",
    params=(Param("period", "RSI length", _I["period"], 2, 100),
            Param("buy_level", "Buy level", _S["entry_cross_above"], 1, 99),
            Param("sell_level", "Sell level", _S["exit_cross_below"], 1, 99)),
    compute=compute, rsi_panel=True,
    panel=(Line("rsi", "RSI", PURPLE), Line("buy_level", "Buy level", "#008300"),
           Line("sell_level", "Sell level", "#c62828")))
