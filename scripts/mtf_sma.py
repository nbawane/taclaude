"""Backtest the multi-timeframe SMA breakout on every symbol in yfinance_prices_daily and write a report.
Rules: src/niftyta/backtest/mtf_sma.py. Prices are split- and dividend-adjusted. Costs: config/costs.yaml.
Each symbol is a separate 100,000 INR account, tested from the first day all three SMAs exist.

Usage: .venv/bin/python scripts/mtf_sma.py [--period 20] [--confirm 3] [--min-bars 250] [--symbols A B]
Output: reports/mtf_sma/ (report.html, by_symbol.csv, trades.csv)
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import yaml

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.data.store import PriceStore  # noqa: E402
from niftyta.pipeline.mtf_sma_run import DAILY_ONLY, HOLD, STRAT, adjusted, run_symbol  # noqa: E402

COLORS = {STRAT: "#2a78d6", DAILY_ONLY: "#1baa7a", HOLD: "#eb6834"}
MIN_SYMBOLS_PER_DAY = 50   # the average-account curve starts once this many stocks are testable


def png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return f'<img src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">'


def style(ax):
    ax.grid(alpha=.25, lw=.6)
    ax.spines[["top", "right"]].set_visible(False)


def table(df: pd.DataFrame, fmt: dict) -> str:
    cells = lambda r: "".join(f"<td>{html.escape(fmt.get(c, str)(r[c]))}</td>" for c in df.columns)
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    return f"<div class=t><table><tr>{head}</tr>{''.join(f'<tr>{cells(r)}</tr>' for _, r in df.iterrows())}</table></div>"


pct = lambda v: "-" if pd.isna(v) else f"{v:.1%}"
num = lambda v: "-" if pd.isna(v) else f"{v:.2f}"
cnt = lambda v: f"{v:,.0f}"


def medians(g: pd.DataFrame) -> dict:
    return {"Stocks": len(g), "Median CAGR": g["cagr"].median(), "Median max drawdown": g["max_drawdown"].median(),
            "Median Sharpe": g["sharpe"].median(), "Profitable stocks": (g["total_return"] > 0).mean(),
            "Median trades": g["trades"].median(), "Time in market": g["exposure"].median()}


def pooled(t: pd.DataFrame) -> dict:
    r = t["return"]
    days = (pd.to_datetime(t["exit_date"]) - pd.to_datetime(t["entry_date"])).dt.days
    return {"Trades": len(t), "Win rate": (r > 0).mean(), "Average trade": r.mean(), "Median trade": r.median(),
            "Average win": r[r > 0].mean(), "Average loss": r[r <= 0].mean(),
            "Profit factor (returns)": r[r > 0].sum() / -r[r <= 0].sum(), "Median calendar days held": days.median()}


PCT = {k: pct for k in ("Median CAGR", "Median max drawdown", "Profitable stocks", "Time in market", "Win rate",
                        "Average trade", "Median trade", "Average win", "Average loss", "Total return", "CAGR",
                        "Max drawdown", STRAT, DAILY_ONLY, HOLD)}
FMT = {**PCT, "Median Sharpe": num, "Sharpe": num, "Profit factor (returns)": num, "Median trades": cnt,
       "Stocks": cnt, "Trades": cnt, "Median calendar days held": cnt}


def main() -> None:
    cfg = yaml.safe_load(open(ROOT / "config" / "strategies.yaml"))["mtf_sma"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=int, default=cfg["period"])
    ap.add_argument("--confirm", type=int, default=cfg["confirm_days"])
    ap.add_argument("--min-bars", type=int, default=250)
    ap.add_argument("--symbols", nargs="*")
    args = ap.parse_args()

    store = PriceStore()
    data = store.conn.execute("SELECT * FROM yfinance_prices_daily ORDER BY symbol, date").df()
    store.close()
    data["date"] = pd.to_datetime(data["date"])
    if args.symbols:
        data = data[data["symbol"].isin([s.upper() for s in args.symbols])]

    rows, trades, curves, skipped, sample = [], [], {STRAT: {}, DAILY_ONLY: {}, HOLD: {}}, [], None
    for symbol, df in data.groupby("symbol"):
        df = adjusted(df.set_index("date").dropna(subset=["open", "high", "low", "close", "adj_close"]))
        out = run_symbol(symbol, df, args.period, args.confirm, args.min_bars)
        if out is None:
            skipped.append(symbol)
            continue
        rows += out[0]
        trades += out[2]
        for name, eq in out[1].items():
            curves[name][symbol] = eq.pct_change()
        if symbol == "RELIANCE" or sample is None:
            sample = (symbol, out[3], out[4], out[1], out[2])
    if not rows:
        sys.exit("no symbol has enough history")
    res, tr = pd.DataFrame(rows), pd.concat(trades, ignore_index=True)
    out_dir = ROOT / "reports" / "mtf_sma"
    out_dir.mkdir(parents=True, exist_ok=True)
    res.to_csv(out_dir / "by_symbol.csv", index=False, float_format="%.4f")
    tr.to_csv(out_dir / "trades.csv", index=False, float_format="%.4f")
    n = res["symbol"].nunique()
    order = [STRAT, DAILY_ONLY, HOLD]
    names = {"full": "Full period", "in_sample": "In sample (first 70%)", "out_of_sample": "Out of sample (last 30%)"}

    def summary(frame):
        return pd.DataFrame([{"Period": names[p], "Strategy": s,
                              **medians(frame[(frame.period == p) & (frame.strategy == s)])}
                             for p in names for s in order])

    summ = summary(res)
    clean = summary(res[~res.big_price_jump])
    pool = pd.DataFrame([{"Strategy": s, **pooled(tr[tr.strategy == s])} for s in order[:2]])

    # average account: equal-weight mean of every stock's daily return
    min_n = min(MIN_SYMBOLS_PER_DAY, n)
    avg = {}
    for s in order:
        m = pd.DataFrame(curves[s]).sort_index()
        avg[s] = m.mean(axis=1)[m.count(axis=1) >= min_n]
    avg = pd.DataFrame(avg).dropna()
    eq = (1 + avg).cumprod() * 100
    port = pd.DataFrame([{"Strategy": s, "Total return": eq[s].iloc[-1] / 100 - 1,
                          "CAGR": (eq[s].iloc[-1] / 100) ** (365.25 / (eq.index[-1] - eq.index[0]).days) - 1,
                          "Max drawdown": (eq[s] / eq[s].cummax() - 1).min(),
                          "Sharpe": avg[s].mean() / avg[s].std() * np.sqrt(252)} for s in order])
    yearly = ((1 + avg).groupby(avg.index.year).prod() - 1).rename_axis("Year").reset_index()

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1.4]})
    for s in order:
        a1.plot(eq[s], color=COLORS[s], lw=1.6, label=s)
        a2.plot((eq[s] / eq[s].cummax() - 1) * 100, color=COLORS[s], lw=1.2)
    a1.set_ylabel("Value (start = 100)"); a1.legend(frameon=False); a2.set_ylabel("Drawdown %"); style(a1); style(a2)
    fig_eq = png(fig)

    fig, ax = plt.subplots(figsize=(11, 4))
    x = np.arange(len(yearly))
    for i, s in enumerate(order):
        ax.bar(x + (i - 1) * .28, yearly[s] * 100, width=.25, color=COLORS[s], label=s)
    ax.set_xticks(x, yearly["Year"]); ax.axhline(0, color="#555", lw=.8); ax.set_ylabel("Return %")
    ax.legend(frameon=False); style(ax)
    fig_year = png(fig)

    fig, ax = plt.subplots(figsize=(11, 3.6))
    r = tr[tr.strategy == STRAT]["return"] * 100
    ax.hist(r.clip(-20, 60), bins=np.arange(-20, 61, 2), color=COLORS[STRAT], edgecolor="white")
    ax.axvline(0, color="#555", lw=.8); ax.set_xlabel("Return per trade % (values beyond -20 or 60 are in the end bars)")
    ax.set_ylabel("Trades"); style(ax)
    fig_hist = png(fig)

    sym, d, sg, _, st = sample
    cut = d.index.max() - pd.DateOffset(years=2)
    v = d[d.index >= cut]
    t = pd.concat(st) if st else pd.DataFrame(columns=["strategy"])
    t = t[(t.strategy == STRAT)]
    t = t[t.entry_date >= cut] if len(t) else t
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(v["close"], color="#222", lw=1, label="Close")
    for col, lab, c in (("sma_d", "Daily SMA", "#2a78d6"), ("sma_w", "Weekly SMA", "#1baa7a"),
                        ("sma_m", "Monthly SMA", "#eb6834")):
        ax.plot(sg.loc[v.index, col], color=c, lw=1.2, label=lab)
    if len(t):
        ax.scatter(t.entry_date, t.entry_price, marker="^", s=70, color="#008300", zorder=5, label="Buy")
        ax.scatter(t.exit_date, t.exit_price, marker="v", s=70, color="#c62828", zorder=5, label="Sell")
    ax.set_ylabel("Adjusted price (INR)"); ax.legend(frameon=False, ncol=3); style(ax)
    fig_sample = png(fig)

    full = res[(res.period == "full")].pivot(index="symbol", columns="strategy", values="cagr")
    full["trades"] = res[(res.period == "full") & (res.strategy == STRAT)].set_index("symbol")["trades"]
    full = full[~full.index.isin(res[res.big_price_jump].symbol)].sort_values(STRAT, ascending=False)
    cols = ["symbol", STRAT, HOLD, "trades"]
    best = table(full.head(10).reset_index()[cols], {**FMT, "trades": cnt})
    worst = table(full.tail(10).iloc[::-1].reset_index()[cols], {**FMT, "trades": cnt})
    f = res[res.period == "full"].pivot(index="symbol", columns="strategy", values=["cagr", "max_drawdown"])
    beats = (f["cagr"][STRAT] > f["cagr"][HOLD]).mean()
    smaller = (f["max_drawdown"][STRAT] > f["max_drawdown"][HOLD]).mean()
    jumps = res[res.big_price_jump].symbol.nunique()

    def headline(p):
        s = summ[summ.Period == names[p]].set_index("Strategy")["Median CAGR"]
        return f"{names[p]}: median yearly return <b>{pct(s[STRAT])}</b> for the strategy, {pct(s[HOLD])} for buy and hold."

    page = f"""<!doctype html><meta charset="utf-8"><title>Multi-timeframe SMA backtest</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:1080px;margin:32px auto;padding:0 16px;color:#1a1a19;background:#fcfcfb}}
img{{max-width:100%}} .t{{overflow-x:auto}} table{{border-collapse:collapse;font-size:13px;margin:8px 0 20px}}
td,th{{border-bottom:1px solid #ddd;padding:5px 10px;text-align:right}} td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){{text-align:left}}</style>
<h1>Multi-timeframe SMA breakout: backtest report</h1>
<p>{n} stocks tested, {len(skipped)} skipped for short history. Data {res['from'].min()} to {res['to'].max()} (Yahoo Finance daily, split and dividend adjusted).</p>
<h2>Summary</h2><ul><li>{headline('full')}</li><li>{headline('out_of_sample')}</li>
<li>The strategy beat buy and hold on yearly return in {pct(beats)} of stocks, and had a smaller drawdown in {pct(smaller)}.</li></ul>
<h2>Rules</h2><ul><li>Buy at the next open after the close has been above the daily SMA({args.period}) for {args.confirm} days in a row (checked on day {args.confirm} only), if that close is also above the SMA({args.period}) of the last completed weekly and monthly candles.</li>
<li>Sell at the next open after a close below the daily SMA({args.period}). Buy only.</li>
<li>Each stock is its own account of 100,000 INR, fully invested per trade, with costs and slippage from config/costs.yaml.</li>
<li>"{DAILY_ONLY}" is the same rule without the weekly and monthly filter, for comparison. All three start on the same day for each stock, once the monthly SMA exists.</li></ul>
<h2>Results by stock (medians)</h2>{table(summ, FMT)}
<h2>All trades pooled (full period)</h2>{table(pool, FMT)}{fig_hist}
<h2>Average account across stocks</h2><p>Mean of all stocks' daily returns, from the first day with at least {min_n} stocks. This assumes daily rebalancing at no cost, so it is a comparison aid, not a tradable portfolio.</p>
{fig_eq}{table(port, FMT)}
<h2>By calendar year (average account)</h2><p>The first and last years are partial.</p>{fig_year}{table(yearly, {**FMT, 'Year': lambda v: str(int(v))})}
<h2>Example: {sym}, last 2 years</h2>{fig_sample}
<h2>Highest and lowest yearly returns</h2><p>Picked after the fact, so not a guide to which stocks will work. Stocks with large one-day price jumps are left out.</p><h3>Top 10</h3>{best}<h3>Bottom 10</h3>{worst}
<h2>Check: without stocks that have large price jumps</h2><p>{jumps} stocks have a one-day move below -35% or above +54%, which may be a data error. Medians without them:</p>{table(clean, FMT)}
<h2>Limitations</h2><ul><li>Survivorship bias: the list is today's Nifty 500, so stocks that failed or dropped out are missing. Returns look better than they would have been, especially buy and hold.</li>
<li>Yahoo prices have not been verified against NSE.</li><li>Costs are assumptions. Taxes on gains are not included. Liquidity and circuit limits are ignored.</li>
<li>One parameter set, not tuned. Past results do not predict future returns.</li></ul>
<p>Skipped: {html.escape(', '.join(skipped) or 'none')}</p>"""
    (out_dir / "report.html").write_text(page)
    print(f"{n} tested, {len(skipped)} skipped, {jumps} with large jumps | beats hold {beats:.0%}, smaller DD {smaller:.0%}")
    with pd.option_context("display.width", 200):
        for t_ in (summ, clean[clean.Period != names['in_sample']], pool.T, port, yearly):
            print(t_.round(3).to_string(), "\n")
    print(out_dir / "report.html")


if __name__ == "__main__":
    main()
