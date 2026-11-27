"""Phase 8: local web app. Run from the project folder:
    .venv/bin/streamlit run app.py
Opens in your browser at http://localhost:8501. Runs only on this machine; nothing is uploaded.
It uses the same analysis code as the command line (scripts/niftyta.py)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from niftyta.backtest.runner import BUY_AND_HOLD  # noqa: E402
from niftyta.data.store import PriceStore  # noqa: E402
from niftyta.indicators.core import load_params  # noqa: E402
from niftyta.nl.parse import parse_prompt  # noqa: E402
from niftyta.pine.generator import generate  # noqa: E402
from niftyta.pipeline.run import analyse  # noqa: E402
from niftyta.reporting.charts import equity_figure  # noqa: E402

st.set_page_config(page_title="NiftyTA", layout="wide")
st.title("NiftyTA: technical analysis and backtesting")
st.caption("Prices are raw NSE data until corporate actions are applied. Results are provisional. "
           "Not financial advice. No orders are placed.")


@st.cache_data(show_spinner=False)
def known_symbols() -> set[str]:
    store = PriceStore()
    rows = store.conn.execute("SELECT DISTINCT symbol FROM prices_daily").fetchall()
    store.close()
    return {r[0] for r in rows}


prompt = st.text_input("Ask in plain English", value="Analyze RELIANCE on the daily timeframe. Apply RSI 14, "
                       "EMA 9/21 and Bollinger Bands. Backtest all three strategies for five years. "
                       "Compare performance. Generate a Pine Script for the best strategy.")
if st.button("Run") or prompt:
    req = parse_prompt(prompt, known_symbols())
    with st.expander("What the app understood", expanded=True):
        st.write({"stocks": req.symbols[:20] + (["..."] if len(req.symbols) > 20 else []),
                  "timeframes": req.timeframes, "strategies": req.strategies, "years": req.years,
                  "pine_script": req.pine})
        for n in req.unsupported:
            st.warning(f"Not supported yet, ignored: {n}")
        for n in req.notes:
            st.info(n)

    if not req.symbols:
        st.stop()
    symbol = st.selectbox("Stock", req.symbols, index=0)
    tf = st.selectbox("Timeframe", req.timeframes, index=0)

    with st.spinner(f"Running {symbol} {tf}..."):
        try:
            a = analyse(symbol, tf, years=req.years)
        except LookupError as e:
            st.error(str(e))
            st.stop()

    adj_msg = (f"Adjusted for {a.adjustments_applied} corporate action(s)." if a.adjusted and a.adjustments_applied
               else "Prices are NOT adjusted for corporate actions. Results are provisional.")
    st.subheader(f"{symbol} {tf}: {a.bars.index.min():%d %b %Y} to {a.bars.index.max():%d %b %Y}")
    st.caption(adj_msg)

    show = a.summary[["period", "strategy", "total_return", "cagr", "max_drawdown", "sharpe",
                      "trades", "win_rate", "profit_factor", "exposure"]]
    st.dataframe(show.round(3), width="stretch", hide_index=True)

    full = [r for r in a.results if r.period == "full"]
    st.plotly_chart(equity_figure({r.strategy: r.result.equity for r in full}), width="stretch")

    if req.pine and len(req.strategies):
        oos = a.summary[(a.summary.period == "out_of_sample") & (a.summary.strategy != BUY_AND_HOLD)].dropna(subset=["sharpe"])
        label_to_key = {"RSI(14) 30/70": "rsi", "EMA 9/21 cross": "ema_cross", "Bollinger 20,2": "bbands"}
        if len(oos):
            best_label = oos.sort_values("sharpe", ascending=False).iloc[0].strategy
            key = label_to_key[best_label]
            source, notes = generate(key, symbol, tf, load_params())
            st.subheader(f"Pine Script: best out-of-sample strategy ({best_label})")
            st.code(source, language="javascript")
            st.download_button("Download .pine", source, file_name=f"{symbol}_{tf}_{key}.pine")
            with st.expander("Pine notes and known differences from Python"):
                st.markdown(notes)
    st.download_button("Download trades (CSV)",
                       pd.concat([r.result.trades.assign(strategy=r.strategy) for r in full
                                  if len(r.result.trades)] or [pd.DataFrame()]).to_csv(index=False),
                       file_name=f"{symbol}_{tf}_trades.csv")
