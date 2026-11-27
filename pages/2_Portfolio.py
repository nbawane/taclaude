"""Portfolio version of the SMA strategy: results of scripts/mtf_sma_optimize.py."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from niftyta.data.store import DEFAULT_DB  # noqa: E402
from niftyta.pipeline.mtf_sma_portfolio import prepare  # noqa: E402
from niftyta.reporting.charts import equity_figure  # noqa: E402
from niftyta.reporting.lw_chart import price_chart  # noqa: E402

OUT = ROOT / "reports" / "mtf_sma_opt"
st.set_page_config(page_title="SMA portfolio", layout="wide")
st.title("SMA strategy as a portfolio")
if not (OUT / "chosen.json").exists():
    st.info("Run first: .venv/bin/python scripts/mtf_sma_optimize.py")
    st.stop()
st.caption("One ₹1 lakh account shared by all stocks, with costs. Today's Nifty 500 list (survivorship bias), "
           "unverified Yahoo prices, no tax. Past results do not predict future returns. Not financial advice.")


def read(name: str, **kw) -> pd.DataFrame:
    return pd.read_csv(OUT / f"{name}.csv", **kw)


def percent(df: pd.DataFrame):
    cols = [c for c in df.select_dtypes("number").columns
            if any(k in c for k in ("cagr", "drawdown", "return", "win_rate", "avg_win", "loss", "exposure"))]
    return df.style.format({c: "{:.1%}" for c in cols}, na_rep="-", precision=2)


st.subheader("Chosen settings")
st.json(json.loads((OUT / "chosen.json").read_text()))
st.subheader("Results")
summary = read("summary")
window = st.radio("Window", ["build", "confirm", "final", "whole period"], horizontal=True)
st.caption("build: used to choose settings. confirm: used to check them. final: looked at once, 2025 onward.")
st.dataframe(percent(summary[summary.window == window][
    ["setup", "cagr", "total_return", "max_drawdown", "calmar", "trades", "win_rate", "profit_factor",
     "avg_win", "avg_loss", "exposure"]]), width="stretch", hide_index=True)

equity = read("equity", parse_dates=["date"], index_col="date")
st.subheader("Account value and drawdown, whole period")
st.plotly_chart(equity_figure({c: equity[c].dropna() for c in equity}), width="stretch")

st.subheader("What was tried")
st.dataframe(percent(read("steps")), width="stretch", hide_index=True)
with st.expander("Every variant"):
    st.dataframe(percent(read("experiments")), width="stretch", hide_index=True)
with st.expander("Robustness: random choice between competing signals (30 runs)"):
    st.dataframe(percent(read("luck").groupby("window")[["cagr", "max_drawdown"]]
                         .quantile([0, .5, 1]).reset_index().rename(columns={"level_1": "quantile (0 = worst)"})),
                 width="stretch", hide_index=True)
with st.expander("Robustness: nearby settings"):
    st.dataframe(percent(read("neighbours")), width="stretch", hide_index=True)

st.subheader("Trades")
trades = read("trades", parse_dates=["entry_date", "exit_date"])
if trades.empty:
    st.info("No closed trades.")
    st.stop()
by_symbol = trades.groupby("symbol")["pnl"].agg(["count", "sum"])
symbol = st.selectbox("Stock", sorted(by_symbol.index),
                      format_func=lambda s: f"{s} ({by_symbol['count'][s]} trades, ₹{by_symbol['sum'][s]:,.0f})")
t = trades[trades.symbol == symbol].sort_values("entry_date")
with duckdb.connect(str(DEFAULT_DB), read_only=True) as conn:
    raw = conn.execute("SELECT * FROM yfinance_prices_daily WHERE symbol = ? ORDER BY date", [symbol]).df()
raw["date"] = pd.to_datetime(raw["date"])
bars = prepare(raw.set_index("date").dropna(subset=["open", "high", "low", "close", "adj_close"]))
st.caption("Dashed red = stop at entry; dashed green = target, if the chosen exit has one. Trailing stops move "
           "after entry and are not drawn. Prices are adjusted to the latest data.")
shown = bars.loc[t.entry_date.min() - pd.DateOffset(months=6):]
price_chart(shown, shown, t, title=symbol, visible_years=10, levels=True).load()
st.dataframe(percent(t.drop(columns="symbol")), width="stretch", hide_index=True)
