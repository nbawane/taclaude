from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

from ..backtest.costs import load_costs
from ..backtest.metrics import PERIODS_PER_YEAR
from ..backtest.runner import PeriodResult, run_all, summary_frame
from ..data.corporate_actions import adjust_bars, load_actions
from ..data.store import PriceStore
from ..data.timeframes import resample_ohlcv
from ..indicators.core import load_params

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class Analysis:
    symbol: str
    timeframe: str
    years: int
    bars: pd.DataFrame            # closed bars only, adjusted
    results: list[PeriodResult]
    summary: pd.DataFrame
    adjustments_applied: int
    adjusted: bool               # True when a corporate-actions file was present and applied
    params: dict = field(default_factory=dict)
    strategies: dict = field(default_factory=dict)
    costs: dict = field(default_factory=dict)


def analyse(symbol: str, timeframe: str = "1D", years: int = 10, store: PriceStore | None = None) -> Analysis:
    symbol = symbol.upper()
    if timeframe not in PERIODS_PER_YEAR:
        raise ValueError(f"timeframe must be one of {list(PERIODS_PER_YEAR)}")
    own = store is None
    store = store or PriceStore()
    end = date.today() + timedelta(days=1)
    try:
        start = end.replace(year=end.year - years)
    except ValueError:
        start = end.replace(year=end.year - years, day=28)
    try:
        daily = store.load(symbol, start, end)
    finally:
        if own:
            store.close()
    if daily.empty:
        raise LookupError(f"No stored data for {symbol}. Run scripts/sync_daily.py first.")

    actions = load_actions()
    daily, applied = adjust_bars(daily, actions, symbol)
    bars = resample_ohlcv(daily, timeframe)
    bars = bars[~bars["partial"]]
    strategies = yaml.safe_load(open(ROOT / "config" / "strategies.yaml"))
    params = load_params()
    results = run_all(bars, params, strategies, PERIODS_PER_YEAR[timeframe])
    return Analysis(symbol, timeframe, years, bars, results, summary_frame(results),
                    applied, actions is not None, params, strategies, load_costs())
