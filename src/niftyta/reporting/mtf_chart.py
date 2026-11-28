"""One chart per timeframe (longest first), stacked vertically or side by side, with crosshairs synced by date.

Built directly on TradingView's Lightweight Charts (the copy bundled with lightweight-charts-python), because
all charts must live in one page to share the pointer."""
from __future__ import annotations

import json
from pathlib import Path

import lightweight_charts
import pandas as pd
import streamlit as st

from ..pipeline import tester
from ..strategies import Strategy
from . import rsi_guides
from .lw_chart import trade_markers

LIBRARY = Path(lightweight_charts.__file__).parent / "js" / "lightweight-charts.js"
TEMPLATE = Path(__file__).with_name("mtf_chart.html")
RANK = {"1D": 0, "1W": 1, "1M": 2}
LAYOUTS = {"vertical": "Vertical (stacked)", "horizontal": "Horizontal (side by side)"}


def _seconds(date) -> int:
    return int(pd.Timestamp(date).normalize().timestamp())


def _points(series: pd.Series) -> list[dict]:
    """Every date is kept (blank where there is no value) so a pane's bars line up with its candles."""
    return [{"time": _seconds(d)} if pd.isna(v) else {"time": _seconds(d), "value": round(float(v), 2)}
            for d, v in series.items()]


def _pane(rule: str, title: str, bars: pd.DataFrame, overlays, panel, months: int, rsi: bool) -> dict:
    return {
        "rsi": rsi and bool(panel),
        "rank": RANK[rule], "title": title, "months": months,
        "candles": [{"time": _seconds(d), "open": round(o, 2), "high": round(h, 2), "low": round(low, 2),
                     "close": round(c, 2)}
                    for d, o, h, low, c in bars[["open", "high", "low", "close"]].itertuples()],
        "overlays": [{"label": x.label, "color": x.color, "data": _points(bars[x.column])} for x in overlays],
        "panel": [{"label": x.label, "color": x.color, "data": _points(bars[x.column])} for x in panel],
        "markers": [], "levels": [], "used": [],
    }


def chart_data(strategy: Strategy, frame: pd.DataFrame, params: dict, trades: pd.DataFrame, open_trade=None,
               levels: bool = False) -> list[dict]:
    """frame: a prepared daily frame (tester.prepare). Returns the panes, longest timeframe first, daily last."""
    panes = []
    for tf in strategy.timeframes:
        view = tester.timeframe_view(frame, tf, params, include_forming=True)
        pane = _pane(tf.rule, tf.title, view, tf.overlays, tf.panel, 120 if tf.rule == "1M" else 36,
                     strategy.rsi_panel)
        if len(view) and view["forming"].iloc[-1]:      # fainter, and labelled in the legend
            up = view["close"].iloc[-1] >= view["open"].iloc[-1]
            faint = "rgba(38,166,154,0.45)" if up else "rgba(239,83,80,0.45)"
            pane["candles"][-1].update(color=faint, wickColor=faint)
            pane["forming"] = {"time": pane["candles"][-1]["time"], "asof": _seconds(frame.index.max())}
        panes.append(pane)
    daily = _pane("1D", "Daily", frame, strategy.overlays, strategy.panel, 12, strategy.rsi_panel)
    daily["markers"] = [{"time": _seconds(m["time"]), "position": m["position"] + "Bar",
                         "shape": m["shape"].replace("_u", "U").replace("_d", "D"), "color": m["color"],
                         "text": m["text"]} for m in trade_markers(trades, open_trade)]
    if levels:
        for t in trades.to_dict("records"):
            days = frame.loc[t["entry_date"]:t["exit_date"]].index
            for key, color in (("stop", "#c62828"), ("target", "#008300")):
                value = t.get(key)
                if len(days) and value is not None and pd.notna(value) and abs(value) != float("inf"):
                    daily["levels"].append({"color": color, "data": _points(pd.Series(float(value), index=days))})
    # the higher-timeframe values the daily rules used on each day (last completed candle before it)
    daily["used"] = [{"label": f"{tf.title} value used", "data": _points(frame[tf.column])}
                     for tf in strategy.timeframes]
    return panes + [daily]


def html(panes: list[dict], title: str = "", layout: str = "vertical") -> str:
    if layout not in LAYOUTS:
        raise ValueError(f"layout must be one of {list(LAYOUTS)}")
    payload = json.dumps({"layout": layout, "title": title, "panes": panes, "band": rsi_guides.BAND, "guides": rsi_guides.LINES},
                         allow_nan=False).replace("</", "<\\/")
    return (TEMPLATE.read_text().replace("/*LIBRARY*/", LIBRARY.read_text()).replace('"/*DATA*/"', payload))


def height(panes: list[dict], layout: str = "vertical") -> int:
    toolbar = 36                             # the full screen button
    if layout == "horizontal":
        return toolbar + 720
    return toolbar + 490 * (len(panes) - 1) + 640   # each higher timeframe 480 + gap, then the daily chart


def show(strategy: Strategy, frame: pd.DataFrame, params: dict, trades: pd.DataFrame, open_trade=None,
         levels: bool = False, title: str = "") -> None:
    layout = st.radio("Chart layout", list(LAYOUTS), format_func=LAYOUTS.get, horizontal=True, key="mtf_layout")
    panes = chart_data(strategy, frame, params, trades, open_trade, levels)
    st.iframe(html(panes, title, layout), height=height(panes, layout))
