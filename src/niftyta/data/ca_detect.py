"""Detect likely splits and bonus issues from our own stored prices (no external source).

A split or bonus makes the unadjusted close jump overnight by a clean ratio (1:1 bonus -> 0.50,
1:10 split -> 0.10, and so on). This finds such jumps and proposes the price factor. It cannot see
small events (dividends, rights issues, demergers whose price effect is modest) and it cannot tell
a real crash from a corporate action by price alone, so every row is a CANDIDATE for human review.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# price factor for bars before the ex-date  ->  human description
CLEAN_FACTORS = {
    2 / 3: "bonus 1:2", 0.5: "bonus 1:1 / split 2:1", 0.4: "split 5:2", 1 / 3: "bonus 2:1 / split 3:1",
    0.25: "bonus 3:1 / split 4:1", 0.2: "split 5:1 / bonus 4:1", 0.1: "split 10:1", 0.05: "split 20:1",
}
# Mild overnight falls (0.70 to 1.0) and rallies happen on ordinary market days (crashes, circuit
# limits), so price alone cannot call them corporate actions. Only large falls are considered.
MAX_RATIO = 0.70
CLEAN_TOLERANCE = 0.08   # the stock also moves a few percent on the ex-date itself


def nearest_clean_factor(ratio: float) -> tuple[float, str, float]:
    """(factor, description, relative error) of the closest clean ratio."""
    best = min(CLEAN_FACTORS, key=lambda f: abs(np.log(ratio / f)))
    return best, CLEAN_FACTORS[best], abs(ratio / best - 1)


def find_candidates(prices: pd.DataFrame) -> pd.DataFrame:
    """prices: long format with columns symbol, date, close, volume (one row per symbol per session)."""
    df = prices.sort_values(["symbol", "date"]).copy()
    g = df.groupby("symbol", sort=False)
    df["prev_close"] = g["close"].shift(1)
    df["avg_vol20"] = g["volume"].transform(lambda s: s.shift(1).rolling(20, min_periods=5).mean())
    df["ratio"] = df["close"] / df["prev_close"]
    df["vol_ratio"] = df["volume"] / df["avg_vol20"]
    hit = df[df["ratio"] <= MAX_RATIO].copy()
    rows = []
    for _, r in hit.iterrows():
        factor, desc, err = nearest_clean_factor(r["ratio"])
        clean = err <= CLEAN_TOLERANCE
        # splits and bonuses increase share count, so volume usually jumps by about 1/factor
        vol_supports = bool(pd.notna(r["vol_ratio"]) and r["vol_ratio"] >= 1.3)
        rows.append({
            "symbol": r["symbol"], "ex_date": pd.Timestamp(r["date"]).date(),
            "prev_close": round(r["prev_close"], 2), "close": round(r["close"], 2),
            "ratio": round(r["ratio"], 4), "suggested_factor": round(factor, 4),
            "pattern": desc, "ratio_error": round(err, 4),
            "volume_vs_20d_avg": None if pd.isna(r["vol_ratio"]) else round(r["vol_ratio"], 2),
            "confidence": ("high" if (clean and vol_supports) else "medium: volume did not jump" if clean
                           else "review: not a clean ratio, could be a crash"),
            "confirmed": "",   # fill in yes/no when reviewing
        })
    return pd.DataFrame(rows)
