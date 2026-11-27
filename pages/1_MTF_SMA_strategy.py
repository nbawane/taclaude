"""Interactive view of the multi-timeframe SMA strategy. Opened from the app: .venv/bin/streamlit run app.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402
import yaml  # noqa: E402

from niftyta.data.store import DEFAULT_DB  # noqa: E402
from niftyta.pipeline.mtf_sma_run import DAILY_ONLY, HOLD, STRAT, adjusted, run_symbol  # noqa: E402
from niftyta.reporting.charts import equity_figure  # noqa: E402
from niftyta.reporting.lw_chart import price_chart  # noqa: E402

st.set_page_config(page_title="MTF SMA strategy", layout="wide")
st.title("Monthly + weekly + daily SMA strategy")
st.caption("Buy at the next open after N daily closes above the daily SMA, if the close is also above the weekly and "
           "monthly SMAs. Sell at the next open after a close below the daily SMA. Yahoo Finance adjusted daily data. "
           "Not financial advice.")


def query(sql: str, params: list | None = None) -> pd.DataFrame:
    with duckdb.connect(str(DEFAULT_DB), read_only=True) as conn:
        return conn.execute(sql, params or []).df()


@st.cache_data(show_spinner=False)
def symbols() -> list[str]:
    return query("SELECT DISTINCT symbol FROM yfinance_prices_daily ORDER BY symbol")["symbol"].tolist()


@st.cache_data(show_spinner=False)
def bars(symbol: str) -> pd.DataFrame:
    df = query("SELECT * FROM yfinance_prices_daily WHERE symbol = ? ORDER BY date", [symbol])
    df["date"] = pd.to_datetime(df["date"])
    return adjusted(df.set_index("date").dropna(subset=["open", "high", "low", "close", "adj_close"]))


cfg = yaml.safe_load(open(ROOT / "config" / "strategies.yaml"))["mtf_sma"]
names = symbols()
symbol = st.sidebar.selectbox("Stock", names, index=names.index("RELIANCE") if "RELIANCE" in names else 0)
period = st.sidebar.number_input("SMA length", 2, 50, cfg["period"])
confirm = st.sidebar.number_input("Closes above the daily SMA", 1, 10, cfg["confirm_days"])
st.sidebar.caption("Picking settings by which looks best here will overfit past data.")

one, all_stocks = st.tabs(["One stock", "All stocks"])

with one:
    out = run_symbol(symbol, bars(symbol), int(period), int(confirm), min_bars=250)
    if out is None:
        st.warning(f"{symbol} doesn't have enough history for SMA {period} on monthly candles.")
    else:
        rows, equity, trades, d, smas, open_entries = out
        res = pd.DataFrame(rows)
        t = next((x for x in trades if x["strategy"].iloc[0] == STRAT), pd.DataFrame())
        full = res[res.period == "full"].set_index("strategy")
        cols = st.columns(4)
        cols[0].metric("Yearly return", f"{full.cagr[STRAT]:.1%}", f"Buy and hold {full.cagr[HOLD]:.1%}",
                       delta_color="off")
        cols[1].metric("Max drawdown", f"{full.max_drawdown[STRAT]:.1%}",
                       f"Buy and hold {full.max_drawdown[HOLD]:.1%}", delta_color="off")
        cols[2].metric("Closed trades", f"{len(t)}")
        cols[3].metric("Win rate", "-" if t.empty else f"{(t['return'] > 0).mean():.1%}")
        st.subheader(f"{symbol}: price and trades")
        st.caption("Scroll to zoom, drag to move back in time, drag the price scale to stretch it. "
                   "Green arrow = buy; red arrow = sell, with the trade's return. Blue = daily SMA, purple = weekly, "
                   "orange = monthly.")
        price_chart(d, smas, t, open_entries.get(STRAT), title=symbol).load()
        st.subheader("Account value and drawdown")
        st.plotly_chart(equity_figure(equity), width="stretch")
        st.subheader("Results by period")
        st.dataframe(res[["period", "strategy", "from", "to", "total_return", "cagr", "max_drawdown", "sharpe",
                          "trades", "win_rate", "profit_factor", "exposure"]].round(3), width="stretch",
                     hide_index=True)
        st.subheader("Trades")
        if t.empty:
            st.info("No closed trades.")
        else:
            st.dataframe(t[["entry_date", "entry_price", "exit_date", "exit_price", "shares", "pnl", "return"]]
                         .round({"entry_price": 2, "exit_price": 2, "pnl": 0, "return": 4}), width="stretch",
                         hide_index=True)

with all_stocks:
    path = ROOT / "reports" / "mtf_sma" / "by_symbol.csv"
    if not path.exists():
        st.info("Run first: .venv/bin/python scripts/mtf_sma.py")
    else:
        saved = pd.read_csv(path)
        st.caption("From the last run of scripts/mtf_sma.py. The sidebar settings don't change this tab.")
        part = st.radio("Period", ["full", "in_sample", "out_of_sample"], horizontal=True)
        other = st.radio("Compare the strategy with", [HOLD, DAILY_ONLY], horizontal=True)
        p = saved[saved.period == part].pivot(index="symbol", columns="strategy", values="cagr") * 100
        fig = px.scatter(p.reset_index(), x=other, y=STRAT, hover_name="symbol", opacity=.65,
                         labels={other: f"{other}: yearly return %", STRAT: "Strategy: yearly return %"})
        lo, hi = p[[other, STRAT]].min().min(), p[[other, STRAT]].max().max()
        fig.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi, line=dict(dash="dot", color="#777"))
        fig.update_layout(height=600)
        st.plotly_chart(fig, width="stretch")
        st.caption(f"Each dot is a stock. Dots above the dotted line did better with the strategy: "
                   f"{(p[STRAT] > p[other]).mean():.0%} of {len(p)} stocks.")
        st.dataframe(p.round(1).reset_index(), width="stretch", hide_index=True)
