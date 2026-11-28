import pandas as pd

from ..backtest.engine import Result
from ..backtest.gfs import build_signals, rsi_series, simulate
from .base import BLUE, ORANGE, PURPLE, Line, Param, Strategy, Timeframe, config

_C = config()["gfs"]
_MODES = ((1, "1: standard GFS"), (2, "2: GFS + RSI divergence"))
_EXITS = (("A", f"A: {_C['exit_rr']}x risk target"),
          ("B", f"B: sell half at RSI {_C['scale_rsi']}, rest below {_C['rest_exit_rsi']}"))


def _settings(p: dict) -> dict:
    return {**_C, **{k: p[k] for k in ("htf_rsi_min", "pullback_low", "pullback_high")}}


def compute(bars: pd.DataFrame, p: dict) -> pd.DataFrame:
    cfg = _settings(p)
    s = build_signals(bars, cfg)
    out = pd.DataFrame({"rsi_day": s.son_rsi, "rsi_week": s.f_rsi, "rsi_month": s.gf_rsi}, index=bars.index)
    out["entry"] = s.mode1 if p["mode"] == 1 else s.mode2
    out["exit"] = False                      # exits are handled by execute()
    return out


def execute(frame: pd.DataFrame, p: dict, cash: float) -> Result:
    """Buy stop above the alert candle, stop below its low, then exit A or B (see gfs_spec.md)."""
    res = simulate(frame, frame["entry"].to_numpy(bool), _settings(p), p["exit_mode"], initial_cash=cash,
                   rsi=frame["rsi_day"].to_numpy())
    if p["exit_mode"] == "B" and len(res.trades):
        res.trades["target"] = float("nan")  # exit B has no price target
    return res


def _higher(column: str, color: str):
    """RSI on that timeframe's own completed candles."""
    def values(bars: pd.DataFrame, p: dict) -> pd.DataFrame:
        return pd.DataFrame({column: rsi_series(bars, _C["rsi_period"])}, index=bars.index)
    return values, (), (Line(column, "RSI", color),)


STRATEGY = Strategy(
    key="gfs", name="GFS (month, week, day RSI)", order=5,
    rules="Monthly and weekly RSI (completed candles) above the minimum, after daily RSI pulled back into the zone. "
          "Mode 1 needs a bullish candle with rising RSI; mode 2 needs a bullish RSI divergence. Entry is a buy stop "
          "above that candle's high, valid for 2 days; the stoploss is its low.",
    params=(Param("mode", "Trigger mode", 1, 1, 2, _MODES),
            Param("exit_mode", "Exit", "A", None, None, _EXITS),
            Param("htf_rsi_min", "Monthly and weekly RSI above", _C["htf_rsi_min"], 1, 99),
            Param("pullback_low", "Daily pullback zone: low", _C["pullback_low"], 1, 99),
            Param("pullback_high", "Daily pullback zone: high", _C["pullback_high"], 1, 99)),
    compute=compute, execute=execute, rsi_panel=True,
    panel=(Line("rsi_day", "Daily RSI", BLUE),),
    timeframes=(Timeframe("1M", "Monthly", "rsi_month", *_higher("rsi_month", ORANGE)),
                Timeframe("1W", "Weekly", "rsi_week", *_higher("rsi_week", PURPLE))))
