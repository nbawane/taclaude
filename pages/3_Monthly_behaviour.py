"""How each instrument moves month by month. Data: scripts/build_monthly_moves.py."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from niftyta.analysis.monthly import (MONTHS, by_calendar_month, expected_by_chance, month_outlook, movers,  # noqa: E402
                                      overall)
from niftyta.data.store import DEFAULT_DB  # noqa: E402

GROUPS = ("Futures", "Indian indices", "Global indices", "Commodities", "Currency", "Stocks")
UP, DOWN = "#1a9850", "#d73027"
DIVERGING = [[0, DOWN], [0.5, "#f7f7f7"], [1, UP]]
MEASURES = {"return_pct": "Move (close to close)", "range_pct": "Range (high to low)",
            "up_pct": "Highest rise in the month", "down_pct": "Deepest fall in the month"}

st.set_page_config(page_title="Monthly behaviour", layout="wide")
st.title("Monthly behaviour")


def query(sql: str, params: list | None = None) -> pd.DataFrame:
    with duckdb.connect(str(DEFAULT_DB), read_only=True) as conn:
        return conn.execute(sql, params or []).df()


try:
    info = query("SELECT * FROM monthly_instruments ORDER BY symbol")
except duckdb.CatalogException:
    st.info("Run first: .venv/bin/python scripts/build_monthly_moves.py")
    st.stop()


def heatmap(z: pd.DataFrame, diverging: bool, height: int):
    values = z.to_numpy(float)
    limit = float(pd.Series(values.ravel()).abs().quantile(0.95)) or 1.0
    scale = dict(colorscale=DIVERGING, zmin=-limit, zmax=limit) if diverging else dict(colorscale="Blues", zmin=0,
                                                                                       zmax=limit)
    fig = go.Figure(go.Heatmap(z=values, x=list(z.columns), y=[str(i) for i in z.index], texttemplate="%{z:.1f}",
                               hovertemplate="%{y} %{x}: %{z:.2f}%<extra></extra>", xgap=2, ygap=2,
                               colorbar=dict(title="%"), **scale))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(autorange="reversed"),
                      xaxis=dict(side="top"))
    return fig


@st.cache_data(show_spinner=False, ttl=600)
def all_moves() -> pd.DataFrame:
    return query("SELECT * FROM monthly_moves")


COLUMNS = {"symbol": "Instrument", "years_up": "Years up", "years": "Of years", "median_return": "Median move %",
           "avg_return": "Average move %", "avg_up_move": "Average rise %", "avg_down_move": "Average fall %",
           "typical_range": "Typical range %", "best": "Best %", "worst": "Worst %", "so_far": "This month so far %"}

quick, one, many = st.tabs(["This month and next", "One instrument", "Compare instruments by month"])

with quick:
    today = pd.Timestamp.today()
    left, middle, right = st.columns([2, 1, 1])
    universe = left.radio("Show", ["Indices, futures, commodities and currency", "Stocks"], horizontal=True)
    often = middle.slider("Same direction in at least (% of years)", 60, 90, 70, 5)
    min_years = right.slider("Years of history needed", 5, 10, 8)
    members = info[(info.grp == "Stocks") == (universe == "Stocks")]
    moves_all = all_moves()
    moves_all = moves_all[moves_all.symbol.isin(members.symbol)]
    up_rate = float((moves_all[moves_all.complete]["return_pct"] > 0).mean())
    flagged = set(members[members.note.str.contains("UNRELIABLE")].symbol)
    st.warning("These are past tendencies, not forecasts. About 10 years per month is a very small sample, so many "
               "patterns appear by luck.")

    periods = (today.to_period("M"), today.to_period("M") + 1)
    for col_tab, period, title in zip(st.tabs([f"{p.strftime('%B %Y')} ({w})" for p, w in
                                               zip(periods, ("this month", "next month"))]),
                                      periods, ("this", "next")):
        with col_tab:
            outlook = month_outlook(moves_all, period.month, min_years)
            if outlook.empty:
                st.info("Not enough history.")
                continue
            now = moves_all[(moves_all.year == period.year) & (moves_all.month == period.month)]
            extra = []
            if len(now):
                outlook = outlook.merge(now[["symbol", "return_pct"]].rename(columns={"return_pct": "so_far"}),
                                        on="symbol", how="left")
                extra = ["so_far"]
                last = members.data_to.max()
                st.caption(f"{period.strftime('%B')} is under way: 'so far' uses prices up to "
                           f"{pd.Timestamp(last):%d %b %Y} (some instruments end earlier) and is not part of the history.")
            outlook["symbol_shown"] = [f"{s} (unreliable data)" if s in flagged else s for s in outlook.symbol]
            lists = movers(outlook, often)
            by_luck = expected_by_chance(outlook, up_rate, often)
            for key, heading, luck in (("rise", f"Usually rose in {period.strftime('%B')}", by_luck[0]),
                                       ("fall", f"Usually fell in {period.strftime('%B')}", by_luck[1]),
                                       ("swing", "Biggest swings (high to low)", None)):
                st.subheader(heading)
                frame = lists[key]
                if luck is not None:
                    st.caption(f"{len(frame)} of {len(outlook)} instruments qualify. Pure chance would produce about "
                               f"{luck:.0f} (rough guide: instruments often move together).")
                if frame.empty:
                    st.write("None.")
                    continue
                shown = ["symbol_shown", "years_up", "years", "median_return", "avg_up_move", "avg_down_move",
                         "typical_range", "best", "worst", *extra]
                table = frame[shown].rename(columns={**COLUMNS, "symbol_shown": "Instrument"}).round(2)
                st.dataframe(table.head(15), width="stretch", hide_index=True)
                st.download_button(f"Download all {len(frame)} (CSV)", table.to_csv(index=False),
                                   f"{period}_{key}.csv", key=f"{title}_{key}")

with one:
    left, right = st.columns([1, 2])
    group = left.selectbox("Group", GROUPS)
    names = info[info.grp == group]["symbol"].tolist()
    default = names.index("NSE:NIFTY1!") if "NSE:NIFTY1!" in names else 0
    symbol = right.selectbox("Instrument", names, index=default)
    row = info[info.symbol == symbol].iloc[0]
    if row.note:
        st.warning(row.note)
    moves = query("SELECT * FROM monthly_moves WHERE symbol = ? ORDER BY year, month", [symbol])
    o = overall(moves)
    st.caption(f"{o['months']} completed months, {row.first_month} to {row.last_month}. Prices up to "
               f"{pd.Timestamp(row.data_to):%d %b %Y}.")
    c = st.columns(6)
    c[0].metric("Typical monthly move", f"{o['typical_move']:.1f}%", help="Median size of the move, up or down")
    c[1].metric("Typical monthly range", f"{o['typical_range']:.1f}%", help="Median high-to-low distance")
    c[2].metric("Months up", f"{o['times_up']:.0f}%")
    c[3].metric("Average up month", f"{o['avg_gain']:+.1f}%")
    c[4].metric("Average down month", f"{o['avg_loss']:+.1f}%")
    c[5].metric("Best / worst", f"{o['best']:+.0f}% / {o['worst']:+.0f}%")

    st.subheader("Every month")
    measure = st.radio("Show", list(MEASURES), format_func=MEASURES.get, horizontal=True)
    grid = moves.pivot(index="year", columns="month", values=measure).reindex(columns=range(1, 13))
    grid.columns = list(MONTHS)
    st.plotly_chart(heatmap(grid, measure != "range_pct", 90 + 34 * len(grid)), width="stretch")
    if not moves["complete"].all():
        st.caption("Includes the unfinished current month. It isn't counted in any summary.")

    st.subheader("By calendar month")
    s = by_calendar_month(moves)
    fig = go.Figure(go.Bar(x=s.month_name, y=s.avg_return, marker_color=[UP if v > 0 else DOWN for v in s.avg_return],
                           customdata=s[["times_up", "years"]],
                           hovertemplate="%{x}: average %{y:+.2f}%<br>up %{customdata[0]:.0f}% of %{customdata[1]} "
                                         "years<extra></extra>", text=[f"{v:+.1f}" for v in s.avg_return]))
    fig.update_layout(height=360, yaxis_title="Average move %", margin=dict(l=10, r=10, t=30, b=10),
                      title="Average move")
    st.plotly_chart(fig, width="stretch")
    fig = go.Figure()
    for col, label, color in (("avg_up_move", "Average rise to the month's high", UP),
                              ("avg_down_move", "Average fall to the month's low", DOWN)):
        fig.add_trace(go.Bar(x=s.month_name, y=s[col], name=label, marker_color=color,
                             hovertemplate="%{x}: %{y:+.2f}%<extra></extra>"))
    fig.update_layout(height=360, barmode="relative", yaxis_title="% from previous close",
                      margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, width="stretch")
    st.caption("Each month has only about 10 observations, so these averages can be driven by one or two years. "
               "They describe the past and are not a forecast.")
    labels = {"month_name": "Month", "years": "Years", "avg_return": "Average move %", "median_return": "Median %",
              "times_up": "Times up %", "best": "Best %", "worst": "Worst %", "avg_up_move": "Average rise %",
              "avg_down_move": "Average fall %", "avg_range": "Average range %", "max_range": "Largest range %"}
    table = s.drop(columns="month").rename(columns=labels).round(2)
    st.dataframe(table, width="stretch", hide_index=True)
    st.download_button("Download this instrument's monthly data (CSV)", moves.to_csv(index=False),
                       f"{symbol.replace('/', '-').replace(':', '_')}_monthly.csv")

with many:
    chosen = st.multiselect("Groups", GROUPS[:-1], default=list(GROUPS[:-1]),
                            help="Stocks are viewed one at a time in the first tab.")
    what = {"avg_return": "Average move %", "times_up": "How often up (%)", "avg_range": "Average range %"}
    pick = st.radio("Value", list(what), format_func=what.get, horizontal=True)
    names = info[info.grp.isin(chosen)]
    if names.empty:
        st.info("Choose at least one group.")
    else:
        everything = query("SELECT * FROM monthly_moves")
        rows = {}
        for g in chosen:
            for sym in names[names.grp == g]["symbol"]:
                rows[sym] = by_calendar_month(everything[everything.symbol == sym]).set_index("month_name")[pick]
        grid = pd.DataFrame(rows).T[list(MONTHS)]
        if pick == "times_up":      # colour around 50%
            fig = heatmap(grid - 50, True, 90 + 30 * len(grid))
            fig.data[0].update(text=grid.round(0).to_numpy(), texttemplate="%{text:.0f}",
                               hovertemplate="%{y} %{x}: up %{text:.0f}% of years<extra></extra>",
                               colorbar=dict(title="vs 50%"))
        else:
            fig = heatmap(grid, pick == "avg_return", 90 + 30 * len(grid))
        st.plotly_chart(fig, width="stretch")
        flagged = names[names.note != ""]
        for r in flagged.itertuples():
            st.caption(f"{r.symbol}: {r.note}")
        st.download_button("Download this table (CSV)", grid.round(2).to_csv(), f"monthly_{pick}.csv")
