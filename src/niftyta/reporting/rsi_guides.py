"""The reference lines every RSI chart carries: 40 and 60 with a faint band between them, and very dotted
20 and 80. Used by all chart code so they look the same everywhere."""
from __future__ import annotations

_QUIET = {"lineWidth": 1, "priceLineVisible": False, "lastValueVisible": False, "crosshairMarkerVisible": False}
_FILL, _CLEAR = "rgba(41,98,255,0.08)", "rgba(0,0,0,0)"
SPARSE_DOTTED = 4       # LightweightCharts.LineStyle.SparseDotted

# A baseline series at 60 with its base at 40 draws the 60 line and fills the band.
BAND = {"level": 60, "options": {**_QUIET, "baseValue": {"type": "price", "price": 40}, "topLineColor": "#787b86",
                                 "topFillColor1": _FILL, "topFillColor2": _FILL,
                                 "bottomLineColor": _CLEAR, "bottomFillColor1": _CLEAR, "bottomFillColor2": _CLEAR}}
LINES = ({"level": 40, "options": {**_QUIET, "color": "#787b86"}},
         {"level": 20, "options": {**_QUIET, "color": "#9598a1", "lineStyle": SPARSE_DOTTED}},
         {"level": 80, "options": {**_QUIET, "color": "#9598a1", "lineStyle": SPARSE_DOTTED}})
