"""Price chart using TradingView's open-source Lightweight Charts (through lightweight-charts-python)."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from lightweight_charts.widgets import StreamlitChart

SMA_LINES = (("sma_d", "Daily SMA", "#2962ff"), ("sma_w", "Weekly SMA", "#8e44ad"),
             ("sma_m", "Monthly SMA", "#f57c00"))
BUY, SELL = "#008300", "#c62828"


def chart_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Date index to a 'time' column in nanoseconds. The library assumes nanoseconds; with pandas 3,
    dates from DuckDB are in microseconds and would all collapse into a few minutes of 1970."""
    out = df.rename_axis("time").reset_index()
    out["time"] = out["time"].astype("datetime64[ns]")
    return out


class _Chart(StreamlitChart):
    def _load(self):   # st.components.v1.html, which the library uses, is deprecated
        st.iframe(f"{self._html}</script></body></html>", height=self.height)


def trade_markers(trades: pd.DataFrame, open_trade=None) -> list[dict]:
    """Buy and sell markers in time order (the chart library requires sorted markers)."""
    marks = []
    for t in trades.to_dict("records"):
        marks.append({"time": t["entry_date"], "position": "below", "shape": "arrow_up", "color": BUY, "text": ""})
        marks.append({"time": t["exit_date"], "position": "above", "shape": "arrow_down", "color": SELL,
                      "text": f"{t['return']:+.1%}"})
    if open_trade:
        marks.append({"time": open_trade[0], "position": "below", "shape": "arrow_up", "color": BUY, "text": "open"})
    return sorted(marks, key=lambda m: m["time"])


def price_chart(bars: pd.DataFrame, smas: pd.DataFrame, trades: pd.DataFrame, open_trade=None,
                title: str = "", height: int = 680, visible_years: int = 1,
                levels: bool = False, overlays=SMA_LINES, panel=()) -> StreamlitChart:
    """Candles, volume, indicator lines (`overlays` on the price, `panel` in a pane below; both are
    (column of `smas`, label, color)) and trade markers. Call .load() to show it in Streamlit.
    levels=True also draws each trade's initial stop and target (columns `stop`, `target`)."""
    chart = _Chart(height=height, inner_height=0.72 if panel else 1)
    chart.layout(background_color="#ffffff", text_color="#222222", font_size=12)
    chart.grid(color="rgba(0,0,0,0.06)")
    chart.candle_style(up_color="#26a69a", down_color="#ef5350", border_up_color="#26a69a",
                       border_down_color="#ef5350", wick_up_color="#26a69a", wick_down_color="#ef5350")
    chart.volume_config(up_color="rgba(38,166,154,0.35)", down_color="rgba(239,83,80,0.35)")
    chart.crosshair(mode="normal")
    chart.legend(visible=True, ohlc=True, percent=True, lines=True, color="#222222", font_size=13, text=title)
    data = bars[["open", "high", "low", "close", "volume"]].round(2)
    chart.set(chart_frame(data))
    def add_lines(target, lines):
        for col, label, color in lines:
            line = target.create_line(name=label, color=color, width=2, price_line=False, price_label=False)
            line.set(chart_frame(smas[col].dropna().round(2).to_frame(label)))

    add_lines(chart, overlays)
    if panel:
        lower = chart.create_subchart(position="bottom", width=1, height=0.28, sync=True)
        lower.layout(background_color="#ffffff", text_color="#222222", font_size=12)
        lower.grid(color="rgba(0,0,0,0.06)")
        lower.legend(visible=True, ohlc=False, percent=False, lines=True, color="#222222", font_size=12)
        add_lines(lower, panel)
    if levels:
        for t in trades.to_dict("records"):
            span = bars.loc[t["entry_date"]:t["exit_date"]].index
            for key, label, color in (("stop", "Stop", SELL), ("target", "Target", BUY)):
                if len(span) and pd.notna(t.get(key)):
                    line = chart.create_line(name=label, color=color, style="dashed", width=2,
                                             price_line=False, price_label=False)
                    line.set(chart_frame(pd.DataFrame({label: round(t[key], 2)}, index=span)))
    marks = trade_markers(trades, open_trade)
    if marks:
        chart.marker_list(marks)
    end = bars.index.max()
    start = max(bars.index.min(), end - pd.DateOffset(years=visible_years))
    chart.set_visible_range(start, end + pd.Timedelta(days=5))
    return chart
