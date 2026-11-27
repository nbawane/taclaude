"""Interactive Plotly charts."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PALETTE = ["#2a78d6", "#1baa7a", "#eb6834", "#8a5cc2"]


def equity_figure(equity: dict[str, pd.Series], colors: dict[str, str] | None = None) -> go.Figure:
    """Account value (start = 100) above drawdown, one line per strategy."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[.7, .3], vertical_spacing=.04)
    for i, (name, series) in enumerate(equity.items()):
        v = series / series.iloc[0] * 100
        line = dict(color=(colors or {}).get(name, PALETTE[i % len(PALETTE)]), width=1.6)
        fig.add_trace(go.Scatter(x=v.index, y=v, name=name, legendgroup=name, line=line,
                                 hovertemplate="%{y:.1f}"), 1, 1)
        fig.add_trace(go.Scatter(x=v.index, y=(v / v.cummax() - 1) * 100, name=name, legendgroup=name,
                                 showlegend=False, line=line, hovertemplate="%{y:.1f}%"), 2, 1)
    fig.update_yaxes(title_text="Value (start = 100)", row=1, col=1)
    fig.update_yaxes(title_text="Drawdown %", row=2, col=1)
    fig.update_layout(height=600, hovermode="x unified", margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.06))
    return fig
