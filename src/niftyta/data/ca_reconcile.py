"""Check split/bonus events from an outside source (Yahoo) against our raw NSE prices.

An event is only trusted when NSE prices show it too. Two independent pieces of evidence:
  jump  the raw NSE overnight close ratio near the date is closer to the factor than to "no change"
  step  the ratio (adjusted other-source close / raw NSE close) moves by the factor across the date.
        Market moves cancel out in this ratio, so it also works for small events (e.g. bonus 1:10).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WINDOW_DAYS = 7        # the outside source's date may differ from NSE's ex-date by a few days
STEP_BARS = 10         # sessions either side used to measure the ratio step
STEP_TOLERANCE = 0.03


def _tolerance(factor: float) -> float:
    """Allowed log-distance between a ratio and the factor: closer to the factor than to 1, capped."""
    return min(0.18, 0.5 * abs(np.log(factor)))


def find_jump(close: pd.Series, date: pd.Timestamp, factor: float) -> tuple[pd.Timestamp | None, float]:
    """(ex-date, raw ratio) of the overnight move near `date` that is closest to `factor`."""
    ratio = (close / close.shift(1)).dropna()
    near = ratio[(ratio.index >= date - pd.Timedelta(days=WINDOW_DAYS)) &
                 (ratio.index <= date + pd.Timedelta(days=WINDOW_DAYS))]
    if near.empty:
        return None, np.nan
    best = (np.log(near) - np.log(factor)).abs().idxmin()
    return best, float(near[best])


def measure_step(nse: pd.Series, other: pd.Series | None, ex_date: pd.Timestamp) -> float:
    """Price factor implied by the two sources: median(other/nse) before / after ex_date."""
    if other is None:
        return np.nan
    r = (other / nse).dropna()
    before, after = r[r.index < ex_date].tail(STEP_BARS), r[r.index >= ex_date].head(STEP_BARS)
    if len(before) < 3 or len(after) < 3:
        return np.nan
    return float(before.median() / after.median())


def judge(nse: pd.Series, other: pd.Series | None, date: pd.Timestamp, factor: float) -> dict:
    """Evidence for one event. status: verified | verified_combined | check | no_evidence | outside_data.
    "factor" is the one to apply: the listed one, except for verified_combined."""
    if date <= nse.index.min() or date > nse.index.max() + pd.Timedelta(days=WINDOW_DAYS):
        return {"status": "outside_data", "factor": factor, "ex_date": date, "nse_ratio": np.nan, "step_factor": np.nan}
    ex_date, ratio = find_jump(nse, date, factor)
    if ex_date is None:
        return {"status": "no_evidence", "factor": factor, "ex_date": date, "nse_ratio": np.nan, "step_factor": np.nan}
    jump_ok = abs(np.log(ratio / factor)) <= _tolerance(factor)
    step = measure_step(nse, other, ex_date if jump_ok else date)
    step_ok = bool(np.isfinite(step) and abs(step / factor - 1) <= STEP_TOLERANCE)
    big = abs(np.log(factor)) >= np.log(1.4)
    if jump_ok and (step_ok or (big and not np.isfinite(step))):
        status = "verified"
    elif jump_ok or step_ok:
        status = "check"
    else:
        status = "no_evidence"
    if status != "verified" and np.isfinite(step) and abs(step / factor - 1) > STEP_TOLERANCE and abs(np.log(step)) > 0.2:
        # e.g. a split and a bonus on one day with only one of them listed: the price series show the total
        both_date, both_ratio = find_jump(nse, date, step)
        if abs(np.log(both_ratio / step)) <= _tolerance(step):
            at_jump = measure_step(nse, other, both_date)
            if abs(at_jump / step - 1) <= STEP_TOLERANCE:
                return {"status": "verified_combined", "factor": at_jump, "ex_date": both_date,
                        "nse_ratio": both_ratio, "step_factor": at_jump}
    return {"status": status, "factor": factor, "ex_date": ex_date if jump_ok else date,
            "nse_ratio": ratio, "step_factor": step}
