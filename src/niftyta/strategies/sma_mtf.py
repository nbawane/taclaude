import pandas as pd

from ..backtest.mtf_sma import signals
from .base import BLUE, ORANGE, PURPLE, Line, Param, Strategy, config

_C = config()["mtf_sma"]


def compute(bars: pd.DataFrame, p: dict) -> pd.DataFrame:
    s = signals(bars, int(p["period"]), int(p["confirm_days"]))
    s["exit_weekly"] = bars["close"] < s["sma_w"]
    return s


STRATEGY = Strategy(
    key="sma_mtf", name="Monthly + weekly + daily SMA", order=1,
    rules="Buy after the close has been above the daily SMA for N days in a row (checked on day N), if it is also "
          "above the SMA of the last completed weekly and monthly candles. Sell on a close below the daily SMA.",
    params=(Param("period", "SMA length", _C["period"], 2, 50),
            Param("confirm_days", "Closes above the daily SMA", _C["confirm_days"], 1, 10)),
    compute=compute,
    overlays=(Line("sma_d", "Daily SMA", BLUE), Line("sma_w", "Weekly SMA", PURPLE),
              Line("sma_m", "Monthly SMA", ORANGE)))
