"""What a strategy must provide to appear in the strategy tester. To add one, create a module in this
folder that defines STRATEGY = Strategy(...). The page, charts and reports pick it up automatically."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd
import yaml

CONFIG = Path(__file__).resolve().parents[3] / "config"
BLUE, PURPLE, ORANGE, GREY = "#2962ff", "#8e44ad", "#f57c00", "#787b86"


def config(file: str = "strategies.yaml") -> dict:
    return yaml.safe_load(open(CONFIG / file))


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    default: float          # an int default gives a whole-number input
    minimum: float
    maximum: float
    choices: tuple = ()     # ((value, label), ...) shows a drop-down instead of a number


@dataclass(frozen=True)
class Line:
    column: str
    label: str
    color: str


@dataclass(frozen=True)
class Timeframe:
    """A higher-timeframe chart of its own: that timeframe's candles with its indicator in a pane below."""
    rule: str               # "1W" or "1M"
    title: str
    column: str             # column of compute() holding the value the daily rules use (needed before trading)
    values: Callable        # values(completed bars, params) -> frame with a column per line below
    overlays: tuple[Line, ...] = ()
    panel: tuple[Line, ...] = ()


@dataclass(frozen=True)
class Strategy:
    key: str
    name: str
    rules: str
    params: tuple[Param, ...]
    # compute(adjusted daily bars, {param: value}) -> frame on the same index with boolean `entry` and `exit`
    # (decided at that close, filled at the next open), one column per indicator line, and optionally
    # boolean `exit_weekly`. A row may only use that day's and earlier data.
    compute: Callable[[pd.DataFrame, dict], pd.DataFrame]
    overlays: tuple[Line, ...] = ()        # drawn on the price
    panel: tuple[Line, ...] = ()           # drawn in a pane below (oscillators)
    order: int = 100                       # position in the strategy list
    # for strategies with their own order types or exits: execute(frame, params, cash) -> engine.Result, one
    # stock at a time. Without it, the shared portfolio engine trades `entry` and `exit`.
    execute: Callable | None = None
    timeframes: tuple[Timeframe, ...] = ()   # extra charts, longest first
    rsi_panel: bool = False                  # the pane below is RSI: draw the standard RSI guide lines

    def defaults(self) -> dict:
        return {p.name: p.default for p in self.params}
