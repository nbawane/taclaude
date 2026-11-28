"""How much an instrument moves in each calendar month. Every move is measured from the previous month's close.

  return_pct  close vs previous close
  up_pct      highest price of the month vs previous close
  down_pct    lowest price of the month vs previous close
  range_pct   (high - low) / previous close

A month with no data for the month before it is left out. The unfinished month is kept, marked
`complete = False`, and never counted in the summaries."""
from __future__ import annotations

from math import comb

import pandas as pd

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MOVES = ("return_pct", "up_pct", "down_pct", "range_pct")


def monthly_moves(daily: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """daily: one instrument, DatetimeIndex, open/high/low/close. as_of: today, to spot the unfinished month."""
    d = daily.sort_index()
    m = d.groupby(d.index.to_period("M")).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                              close=("close", "last"), days=("close", "size"))
    prev = m["close"].shift()
    follows = pd.Series(m.index, index=m.index).diff().apply(lambda x: getattr(x, "n", None)) == 1
    out = m.assign(prev_close=prev,
                   return_pct=(m["close"] / prev - 1) * 100, up_pct=(m["high"] / prev - 1) * 100,
                   down_pct=(m["low"] / prev - 1) * 100, range_pct=(m["high"] - m["low"]) / prev * 100)
    # complete: the month has ended, and the data reaches its last week (not just stopped part way)
    last_day = d.index.max()
    out["complete"] = [p.end_time.normalize() < as_of.normalize() and (p.end_time - last_day).days < 4 for p in m.index]
    out = out[follows.fillna(False).astype(bool)]
    return out.assign(year=out.index.year, month=out.index.month).reset_index(drop=True)


def by_calendar_month(moves: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar month (Jan..Dec) over the completed months."""
    g = moves[moves["complete"]].groupby("month")
    out = pd.DataFrame({
        "years": g.size(),
        "avg_return": g["return_pct"].mean(), "median_return": g["return_pct"].median(),
        "times_up": g["return_pct"].apply(lambda r: (r > 0).mean() * 100),
        "best": g["return_pct"].max(), "worst": g["return_pct"].min(),
        "avg_up_move": g["up_pct"].mean(), "avg_down_move": g["down_pct"].mean(),
        "avg_range": g["range_pct"].mean(), "max_range": g["range_pct"].max(),
    }).reindex(range(1, 13))
    out.insert(0, "month_name", MONTHS)
    return out.rename_axis("month").reset_index()


def overall(moves: pd.DataFrame) -> dict:
    """Typical monthly behaviour across all completed months."""
    m = moves[moves["complete"]]
    r = m["return_pct"]
    return {"months": len(m), "avg_return": r.mean(), "times_up": (r > 0).mean() * 100,
            "avg_gain": r[r > 0].mean(), "avg_loss": r[r <= 0].mean(), "typical_move": r.abs().median(),
            "typical_range": m["range_pct"].median(), "best": r.max(), "worst": r.min()}


def month_outlook(moves: pd.DataFrame, month: int, min_years: int = 8) -> pd.DataFrame:
    """One row per instrument: what it did in this calendar month in earlier, completed years.
    moves needs a `symbol` column. Instruments with fewer than `min_years` such months are left out."""
    g = moves[moves["complete"] & (moves["month"] == month)].groupby("symbol")
    out = pd.DataFrame({
        "years": g.size(), "years_up": g["return_pct"].apply(lambda r: int((r > 0).sum())),
        "median_return": g["return_pct"].median(), "avg_return": g["return_pct"].mean(),
        "avg_up_move": g["up_pct"].mean(), "avg_down_move": g["down_pct"].mean(),
        "typical_range": g["range_pct"].median(), "best": g["return_pct"].max(), "worst": g["return_pct"].min(),
    })
    out = out[out["years"] >= min_years]
    out["times_up"] = out["years_up"] / out["years"] * 100
    return out.reset_index()


def movers(outlook: pd.DataFrame, often: float = 70) -> dict[str, pd.DataFrame]:
    """Three rankings: usually rose, usually fell, and swung the most. The median is used so that one
    extreme year does not decide the order."""
    up = outlook[(outlook["times_up"] >= often) & (outlook["median_return"] > 0)]
    down = outlook[(outlook["times_up"] <= 100 - often) & (outlook["median_return"] < 0)]
    return {"rise": up.sort_values(["times_up", "median_return"], ascending=False),
            "fall": down.sort_values(["times_up", "median_return"], ascending=True),
            "swing": outlook.sort_values("typical_range", ascending=False)}


def expected_by_chance(outlook: pd.DataFrame, up_rate: float, often: float = 70) -> tuple[float, float]:
    """How many instruments would pass the "usually rose" and "usually fell" cut-offs if every year were a coin
    toss that comes up with probability `up_rate`. Treats instruments as independent, which they are not."""
    rise = fall = 0.0
    for n in outlook["years"]:
        for k in range(n + 1):
            p = comb(n, k) * up_rate ** k * (1 - up_rate) ** (n - k)
            share = k / n * 100
            rise += p if share >= often else 0
            fall += p if share <= 100 - often else 0
    return rise, fall
