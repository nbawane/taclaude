"""Run the GFS strategy: trigger mode 1 vs 2, exit mode A vs B, full / in-sample / out-of-sample.
Son timeframe is daily (the default). Triggers come from the full history; each period is
simulated on its own slice of bars, so warm-up data is never traded on."""
from __future__ import annotations

import numpy as np
import pandas as pd
import yaml
from pathlib import Path

from ..backtest.gfs import build_signals, closed_bars, rsi_series, simulate
from ..data.corporate_actions import adjust_bars, load_actions
from ..backtest.metrics import performance
from ..backtest.runner import IN_SAMPLE_FRACTION

ROOT = Path(__file__).resolve().parents[3]
VARIANTS = [("Mode 1 (standard GFS)", "mode1", "A"), ("Mode 1 (standard GFS)", "mode1", "B"),
            ("Mode 2 (GFS + divergence)", "mode2", "A"), ("Mode 2 (GFS + divergence)", "mode2", "B")]


def load_gfs_config() -> dict:
    return yaml.safe_load(open(ROOT / "config" / "strategies.yaml"))["gfs"]


def run_gfs(daily: pd.DataFrame, symbol: str, cfg: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Returns (summary table, {variant name: full-period trades}). Prices are adjusted for
    corporate actions with the same file as the other strategies."""
    cfg = cfg or load_gfs_config()
    daily, _ = adjust_bars(daily, load_actions(), symbol)
    if cfg["son_tf"] != "1D":
        raise NotImplementedError("Only a daily Son timeframe is supported in this runner.")
    sig = build_signals(daily, cfg)
    son = closed_bars(daily, "1D")
    son_rsi_full = pd.Series(sig.son_rsi, index=son.index)  # full-history RSI, sliced per period
    split = son.index[int(len(son) * IN_SAMPLE_FRACTION)]
    periods = {"full": (son.index[0], son.index[-1]),
               "in_sample": (son.index[0], split - pd.Timedelta(days=1)),
               "out_of_sample": (split, son.index[-1])}
    rows, trades = [], {}
    for label, trig_name, ex in VARIANTS:
        trig = sig.mode1 if trig_name == "mode1" else sig.mode2
        for period, (a, b) in periods.items():
            sub = daily[(daily.index >= a) & (daily.index <= b)]
            mask = closed_bars(sub, "1D").index
            trig_sub = pd.Series(trig, index=son.index).reindex(mask).fillna(False).to_numpy(bool)
            res = simulate(sub, trig_sub, cfg, ex, rsi=son_rsi_full.reindex(mask).to_numpy())
            m = performance(res.equity, res.trades, res.exposure, 252)
            R = res.trades["R"].dropna() if len(res.trades) else pd.Series(dtype=float)
            rows.append({"variant": label, "exit": "A (2.5R target)" if ex == "A" else "B (scale 50% at RSI 60)",
                         "period": period, **m, "expectancy_R": float(R.mean()) if len(R) else np.nan,
                         "open_at_end": res.open_at_end})
            if period == "full":
                trades[f"{label} / exit {ex}"] = res.trades.assign(variant=label, exit=ex)
    # buy and hold over the same full period, for reference (standard engine: buy next open, hold)
    from ..backtest.engine import run_backtest
    entries = np.zeros(len(son), bool); entries[0] = True
    bh = run_backtest(son, entries, np.zeros(len(son), bool))
    rows.append({"variant": "Buy and hold", "exit": "-", "period": "full",
                 **performance(bh.equity, bh.trades, bh.exposure, 252), "expectancy_R": np.nan,
                 "open_at_end": bh.open_at_end})
    return pd.DataFrame(rows), trades
