"""The same test layout for every strategy in src/niftyta/strategies/."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from niftyta.backtest.portfolio import PortfolioConfig  # noqa: E402
from niftyta.data.store import DEFAULT_DB  # noqa: E402
from niftyta.pipeline import tester  # noqa: E402
from niftyta.reporting.charts import equity_figure  # noqa: E402
from niftyta.reporting import mtf_chart  # noqa: E402
from niftyta.reporting.lw_chart import price_chart  # noqa: E402
from niftyta.strategies import all_strategies  # noqa: E402

ONE, ALL = "One stock", "All stocks (shared account)"
INDEX = "Nifty 500"
INDICES = ("Nifty 50", "Nifty Bank", INDEX)     # can be tested like a stock

st.set_page_config(page_title="Strategy tester", layout="wide")


def query(sql: str, params: list | None = None) -> pd.DataFrame:
    with duckdb.connect(str(DEFAULT_DB), read_only=True) as conn:
        return conn.execute(sql, params or []).df()


@st.cache_data(show_spinner=False)
def prices() -> dict[str, pd.DataFrame]:
    df = query("SELECT * FROM yfinance_prices_daily ORDER BY symbol, date")
    df["date"] = pd.to_datetime(df["date"])
    return {s: d.set_index("date").dropna(subset=["open", "high", "low", "close", "adj_close"])
            for s, d in df.groupby("symbol")}


@st.cache_data(show_spinner=False)
def index_bars() -> dict[str, pd.DataFrame]:
    """NSE index bars in the same shape as the stock bars (an index has nothing to adjust)."""
    df = query("SELECT index_name, date, open, high, low, close, close AS adj_close, volume FROM index_daily "
               f"WHERE index_name IN ({', '.join('?' * len(INDICES))}) ORDER BY date", list(INDICES))
    df["date"] = pd.to_datetime(df["date"])
    found = {n: d.drop(columns="index_name").set_index("date").dropna(subset=["open", "high", "low", "close"])
             for n, d in df.groupby("index_name")}
    return {n: found[n] for n in INDICES if n in found}


@st.cache_data(show_spinner="Calculating signals...", max_entries=6)
def frames_for(key: str, params: tuple, symbols: tuple) -> dict[str, pd.DataFrame]:
    s = all_strategies()[key]
    bars = {**prices(), **index_bars()}
    return {x: tester.prepare(s, bars[x], dict(params)) for x in symbols}


@st.cache_data(show_spinner="Testing every stock...", max_entries=6)
def every_stock(key: str, params: tuple, cfg: PortfolioConfig, start, end) -> pd.DataFrame:
    strategy = all_strategies()[key]
    frames = frames_for(key, params, tuple(prices()))
    rows = []
    for symbol, f in frames.items():
        ready = tester.first_ready({symbol: f})
        if ready is None or len(f.loc[max(ready, start):end]) < 250:
            continue
        a = max(ready, start)
        _, m = tester.run({symbol: f}, cfg, a, end, strategy, dict(params))
        hold = tester.buy_and_hold(f["close"].loc[a:end])
        rows.append({"symbol": symbol, "strategy": m["cagr"], "buy and hold": hold["cagr"],
                     "strategy drawdown": m["max_drawdown"], "buy and hold drawdown": hold["max_drawdown"],
                     "trades": m["trades"]})
    return pd.DataFrame(rows)


def percent(df: pd.DataFrame):
    cols = [c for c in df.select_dtypes("number").columns
            if any(k in c for k in ("cagr", "drawdown", "return", "win_rate", "strategy", "buy and hold"))]
    return df.style.format({c: "{:.1%}" for c in cols}, na_rep="-", precision=2)


# ---------- sidebar ----------
strategies = all_strategies()
side = st.sidebar
key = side.selectbox("Strategy", list(strategies), format_func=lambda k: strategies[k].name)
strategy = strategies[key]
own = strategy.execute is not None     # has its own entry orders and exits
mode = side.radio("Test on", [ONE] if own else [ONE, ALL])
names = list(prices())                              # stocks only: used for the all-stock tests
symbol = side.selectbox("Stock or index", list(index_bars()) + names) if mode == ONE else None
is_index = symbol in INDICES

side.subheader("Strategy settings")
params = {}
for p in strategy.params:
    if p.choices:
        labels = dict(p.choices)
        params[p.name] = side.selectbox(p.label, list(labels), list(labels).index(p.default),
                                        format_func=labels.get, key=f"{key}_{p.name}")
        continue
    cast = int if isinstance(p.default, int) else float
    params[p.name] = side.number_input(p.label, cast(p.minimum), cast(p.maximum), cast(p.default),
                                       key=f"{key}_{p.name}")
params_key = tuple(sorted(params.items()))

side.subheader("Trade management")
one = mode == ONE
k = "one" if one else "all"
cash = side.number_input("Capital (INR)", 10_000, 100_000_000, 1_000_000 if is_index else 100_000, step=10_000,
                         key=f"cash_{is_index}")
if own:
    side.caption("This strategy sets its own entry, stoploss and exit, and invests all capital in each trade.")
    cfg = PortfolioConfig(max_positions=1, max_position_pct=1.0, initial_cash=float(cash))
else:
    stops = {"none": "No stoploss", "atr": "ATR multiple", "swing": "Recent 10-day low"}
    stop = side.selectbox("Stoploss", list(stops), index=0 if one else 1, format_func=stops.get, key=f"stop_{k}")
    stop_atr = side.number_input("ATR multiple", 0.5, 10.0, 2.0, 0.5) if stop == "atr" else 2.0
    exits = {"sma": "Strategy's sell signal", "target": "Target (multiple of risk)",
             "half_trail": "Half at target, then trail", "atr_trail": "Trailing stop (ATR)"}
    if strategy.key == "sma_mtf":
        exits["weekly"] = "Close below weekly SMA"
    if stop == "none":   # targets are measured in units of the stop distance
        exits = {x: v for x, v in exits.items() if x not in ("target", "half_trail")}
    exit_ = side.selectbox("Exit", list(exits), format_func=exits.get)
    target_r = side.number_input("Target (times risk)", 0.5, 10.0, 3.0, 0.5) if exit_ in ("target", "half_trail") else 3.0
    trail = side.number_input("Trail (ATR multiple)", 0.5, 10.0, 3.0, 0.5) if exit_ in ("atr_trail", "half_trail") else 3.0
    risk = side.number_input("Risk per trade (%)", 0.1, 10.0, 1.0, 0.25, key=f"risk_{k}") / 100 if stop != "none" else 0.01
    positions = 1 if one else side.number_input("Maximum positions", 1, 50, 5)
    max_pct = side.number_input("Maximum in one stock (%)", 1, 100, 100 if one else 25 if stop != "none" else 20,
                                key=f"max_{k}") / 100
    cfg = PortfolioConfig(risk_pct=risk, max_positions=int(positions), max_position_pct=max_pct, stop=stop,
                          stop_atr=stop_atr, exit=exit_, target_r=target_r, trail_atr=trail, initial_cash=float(cash))

frames = frames_for(key, params_key, (symbol,) if one else tuple(names))
ready = tester.first_ready(frames)
last_date = max(f.index.max() for f in frames.values())
st.title(f"Strategy tester: {strategy.name}")
st.caption(strategy.rules + " Orders fill at the next open, with costs and slippage.")
if is_index:
    st.info(f"{symbol} is an index and cannot be bought directly. This test trades whole units at the index level "
            "with share delivery costs. Real trades would use an ETF or futures, so results would differ. "
            f"Index data runs to {last_date:%d %b %Y}.")
if ready is None:
    st.warning("Not enough history for these settings.")
    st.stop()
last = max(f.index.max() for f in frames.values())
default_start = max(ready, pd.Timestamp("2018-07-01")) if not one else ready
default_start = min(default_start, last)
dates = side.date_input("Date range", (default_start.date(), last.date()), min_value=ready.date(),
                        max_value=last.date(), key=f"dates_{key}_{k}_{symbol}_{params_key}")
if len(dates) != 2:
    st.info("Choose both a start and an end date.")
    st.stop()
start, end = pd.Timestamp(dates[0]), pd.Timestamp(dates[1])
out = tester.run(frames, cfg, start, end, strategy, params)
if out is None:
    st.warning("The date range is too short.")
    st.stop()
result, m = out

benchmarks = {INDEX: index_bars()[INDEX]["close"]} if symbol != INDEX else {}
if one:
    benchmarks = {"buy and hold": frames[symbol]["close"], **benchmarks}
bench = {n: tester.buy_and_hold(s.loc[start:end]) for n, s in benchmarks.items() if len(s.loc[start:end]) > 1}

# ---------- 1. summary ----------
st.header("1. Summary")
cols = st.columns(5)
cols[0].metric("Yearly return", f"{m['cagr']:.1%}")
cols[1].metric("Worst fall", f"{m['max_drawdown']:.1%}")
cols[2].metric("Win rate", "-" if pd.isna(m["win_rate"]) else f"{m['win_rate']:.1%}")
cols[3].metric("Profit factor", "-" if pd.isna(m["profit_factor"]) else f"{m['profit_factor']:.2f}")
cols[4].metric("Closed trades", f"{m['trades']}")
compare = pd.DataFrame([{"": "Strategy", **{x: m[x] for x in ("total_return", "cagr", "max_drawdown")}},
                        *({"": n, **b} for n, b in bench.items())])
st.dataframe(percent(compare), width="stretch", hide_index=True)
st.caption(f"Average share of the account invested: {m['exposure']:.0%}. Benchmarks are fully invested with no "
           "costs; the index excludes dividends.")

# ---------- 2. price chart ----------
st.header("2. Price chart")
trades = result.trades
open_now = {p["symbol"]: p for p in result.open_positions}
if not one:
    traded = sorted(set(trades["symbol"] if len(trades) else []) | set(open_now))
    symbol = st.selectbox("Stock to show", traded) if traded else None
if symbol is None:
    st.info("No trades to show.")
else:
    f = frames[symbol].loc[start:end]
    t = trades[trades.symbol == symbol] if len(trades) else trades
    held = open_now.get(symbol)
    st.caption("Scroll to zoom, drag to move. Green arrow = buy, red arrow = sell with the trade's return. Dashed "
               "lines = stop and target at entry; trailing moves are not drawn.")
    open_trade = (held["entry_date"], held["entry_price"]) if held else None
    levels = own or cfg.stop != "none"
    if strategy.timeframes:
        st.caption("One chart per timeframe. Hover on any chart to mark the same time on all of them. Month and week "
                   "show completed candles; the daily legend shows the values the rules used that day.")
        mtf_chart.show(strategy, frames[symbol].loc[:end], params, t, open_trade, levels, symbol)
    else:
        price_chart(f, f, t, open_trade, title=symbol, visible_years=2, levels=levels, height=720,
                    overlays=[(x.column, x.label, x.color) for x in strategy.overlays],
                    panel=[(x.column, x.label, x.color) for x in strategy.panel], rsi=strategy.rsi_panel).load()

# ---------- 3. equity ----------
st.header("3. Account value and drawdown")
curves = {"Strategy": result.equity}
for n, s in benchmarks.items():
    s = s.reindex(result.equity.index, method="ffill").dropna()
    if len(s) > 1:
        curves[n] = s
st.plotly_chart(equity_figure(curves), width="stretch")

# ---------- 4. checks ----------
st.header("4. Honesty checks")
periods = tester.by_period(frames, cfg, benchmarks, start, end, strategy, params)
for text in tester.warnings(m, periods, bench):
    st.warning(text)
st.dataframe(percent(periods), width="stretch", hide_index=True)
st.caption("Each period starts fresh. Trying many settings and keeping the best overfits past data. All-stock tests "
           "use today's Nifty 500 list (survivorship bias). Yahoo prices are unverified. Tax is ignored. "
           "Not financial advice.")

# ---------- 5. trades ----------
st.header("5. Trades")
shown = trades if len(trades) else pd.DataFrame()
if shown.empty:
    st.info("No closed trades.")
else:
    shown = shown.assign(reason=shown["reason"].replace("close below daily SMA", "strategy sell signal"))
    shown = shown.round({"entry_price": 2, "exit_price": 2, "stop": 2, "target": 2, "pnl": 0, "R": 2, "costs": 2})
    shown = shown.replace([float("inf"), float("-inf")], float("nan"))
    st.dataframe(percent(shown), width="stretch", hide_index=True)
    st.download_button("Download trades (CSV)", shown.to_csv(index=False), f"{key}_trades.csv")
if result.open_positions:
    st.write("Still open at the end (counted in the account value):")
    st.dataframe(pd.DataFrame(result.open_positions).replace([float("-inf")], float("nan")), width="stretch",
                 hide_index=True)

# ---------- 6. all stocks ----------
st.header("6. Stock by stock")
st.write("Each stock on its own account, all-in, with the same strategy, stoploss and exit.")
if st.toggle("Run on every stock (takes a while)"):
    solo = PortfolioConfig(**{**cfg.__dict__, "max_positions": 1, "max_position_pct": 1.0})
    table = every_stock(key, params_key, solo, start, end)
    if table.empty:
        st.info("No stock has enough history in this range.")
    else:
        fig = px.scatter(table, x="buy and hold", y="strategy", hover_name="symbol", opacity=.65,
                         hover_data=["trades"])
        lo, hi = table[["buy and hold", "strategy"]].min().min(), table[["buy and hold", "strategy"]].max().max()
        fig.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi, line=dict(dash="dot", color="#777"))
        fig.update_layout(height=600, xaxis_tickformat=".0%", yaxis_tickformat=".0%",
                          xaxis_title="Buy and hold: yearly return", yaxis_title="Strategy: yearly return")
        st.plotly_chart(fig, width="stretch")
        st.write(f"{len(table)} stocks. Median yearly return: strategy {table['strategy'].median():.1%}, buy and hold "
                 f"{table['buy and hold'].median():.1%}. The strategy was higher in "
                 f"{(table['strategy'] > table['buy and hold']).mean():.0%} of stocks.")
        st.dataframe(percent(table), width="stretch", hide_index=True)
