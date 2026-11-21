"""Phase 5: the 11-section backtest report (readme section 3), written as Markdown."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..backtest.runner import BUY_AND_HOLD
from ..pipeline.run import Analysis

RULES = {
    "RSI(14) 30/70": "Buy when RSI(14) crosses above 30. Sell when RSI(14) crosses below 70.",
    "EMA 9/21 cross": "Buy when EMA(9) crosses above EMA(21). Sell when EMA(9) crosses below EMA(21).",
    "Bollinger 20,2": "Buy when the close moves back above the lower band (20, 2 sd) after closing below it. "
                      "Sell when the close moves back below the upper band after closing above it.",
    BUY_AND_HOLD: "Buy at the first bar of each period and hold to the end.",
}
TABLE_COLS = ["strategy", "total_return", "cagr", "max_drawdown", "sharpe", "trades", "win_rate",
              "profit_factor", "exposure"]


def _pct(x):
    return "n/a" if pd.isna(x) else f"{x:+.1%}"


def _num(x, nd=2):
    return "n/a" if pd.isna(x) else f"{x:.{nd}f}"


def _table(df: pd.DataFrame) -> str:
    rows = ["| Strategy | Total return | CAGR | Max drawdown | Sharpe | Trades | Win rate | Profit factor | Exposure |",
            "|---|---|---|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        rows.append(f"| {r.strategy} | {_pct(r.total_return)} | {_pct(r.cagr)} | {_pct(r.max_drawdown)} | "
                    f"{_num(r.sharpe)} | {int(r.trades)} | {'n/a' if pd.isna(r.win_rate) else f'{r.win_rate:.1%}'} | "
                    f"{_num(r.profit_factor)} | {r.exposure:.0%} |")
    return "\n".join(rows)


def build_report(a: Analysis, reports_dir: Path) -> str:
    tag = f"{a.symbol}_{a.timeframe}"
    s = a.summary
    full = s[s.period == "full"].set_index("strategy")
    oos = s[s.period == "out_of_sample"]
    trades_full = int(full.loc[[k for k in full.index if k != BUY_AND_HOLD], "trades"].sum())
    adjusted_note = (f"Adjusted for {a.adjustments_applied} corporate action(s) from data/reference/corporate_actions.csv."
                     if a.adjusted and a.adjustments_applied else
                     "**Prices are NOT adjusted for corporate actions.** Bonus, split and demerger effects "
                     "appear as price falls. Treat every number below as provisional.")
    c = a.costs
    buy_bps = (c["exchange_txn_charge"] + c["sebi_fee"] + c["gst_rate"] * (c["exchange_txn_charge"] + c["sebi_fee"]) + c["stamp_duty_buy"]) * 1e4
    sell_bps = (c["exchange_txn_charge"] + c["sebi_fee"] + c["gst_rate"] * (c["exchange_txn_charge"] + c["sebi_fee"]) + c["stt_delivery"]) * 1e4
    best_oos = oos[oos.strategy != BUY_AND_HOLD].sort_values("total_return", ascending=False).head(1)
    bh_oos = oos[oos.strategy == BUY_AND_HOLD]

    lines = [
        f"# {a.symbol} backtest report: {a.timeframe}",
        "",
        f"_Generated from the local database. {adjusted_note}_",
        "",
        "## 1. Executive summary",
        "",
        f"- Period: {a.bars.index.min():%d %b %Y} to {a.bars.index.max():%d %b %Y}, "
        f"{len(a.bars)} closed {a.timeframe} bars.",
        f"- Buy-and-hold over the full period: {_pct(full.loc[BUY_AND_HOLD, 'total_return'])} "
        f"(CAGR {_pct(full.loc[BUY_AND_HOLD, 'cagr'])}).",
        f"- Strategies placed {trades_full} trades in total across the three rule sets over the full period.",
    ]
    if len(best_oos):
        b = best_oos.iloc[0]
        lines.append(f"- Best out-of-sample strategy: {b.strategy} ({_pct(b.total_return)}, {int(b.trades)} trades). "
                     f"Buy-and-hold out-of-sample: {_pct(bh_oos.total_return.iloc[0])}.")
    lines += ["- Results are a description of past data only. They are not a recommendation to trade.",
              "", "## 2. Data source and date range", "",
              "- Source: NSE daily bhavcopy (end-of-day, official NSE archive), stored in a local DuckDB file.",
              f"- Range: {a.bars.index.min():%Y-%m-%d} to {a.bars.index.max():%Y-%m-%d}, "
              f"{a.years}-year window, {a.timeframe} bars.",
              f"- Corporate-action adjustment: {adjusted_note}",
              "- Missing sessions are never filled. Holidays are NSE's own closed days.",
              "", "## 3. Strategy rules", "",
              "Signals use closed daily bars. Trades execute at the next session's open, with slippage. "
              "Parameters are fixed in config and were not tuned on the test period.", ""]
    for name, text in RULES.items():
        if name in full.index:
            lines.append(f"- **{name}:** {text}")
    lines += ["", "## 4. Performance comparison (full period)", "", _table(s[s.period == "full"][TABLE_COLS]), "",
              "## 5. Equity curve", "", f"![Equity curve](./{tag}_performance.png)", "",
              "## 6. Drawdown chart", "",
              "Drawdown panel in the same image: ![Drawdown](./" + f"{tag}_performance.png)", "",
              "## 7. Trade history", ""]
    trade_csv = reports_dir / f"{tag}_trades.csv"
    rows = []
    for r in a.results:
        if r.period == "full" and len(r.result.trades):
            t = r.result.trades.assign(strategy=r.strategy)
            rows.append(t)
    if rows:
        all_t = pd.concat(rows)
        all_t.to_csv(trade_csv, index=False, float_format="%.4f")
        lines.append(f"All {len(all_t)} trades are in [{trade_csv.name}](./{trade_csv.name}). First 15:")
        lines.append("")
        head = all_t[["strategy", "entry_date", "exit_date", "entry_price", "exit_price", "shares", "pnl", "return"]].head(15)
        lines.append("| " + " | ".join(head.columns) + " |")
        lines.append("|" + "---|" * len(head.columns))
        for _, r in head.iterrows():
            lines.append("| " + " | ".join(str(round(v, 2)) if isinstance(v, float) else str(v)[:10] for v in r.values) + " |")
    else:
        lines.append("No trades in the full period.")
    lines += ["", "## 8. Transaction cost assumptions", "",
              f"- Buy side: about {buy_bps:.1f} bps (exchange, SEBI, GST on those, stamp duty), plus slippage.",
              f"- Sell side: about {sell_bps:.1f} bps (exchange, SEBI, GST, STT), plus slippage.",
              f"- Slippage: {c['slippage_per_side']:.2%} per side. Brokerage: Zerodha delivery, "
              f"{c['brokerage_per_order_inr']} per order (verify).",
              "- All rates are assumptions in `config/costs.yaml`. Verify them before relying on results.", "",
              "## 9. Out-of-sample results", "",
              "Last 30% of bars, with parameters fixed from the full-period configuration.", "",
              _table(oos[TABLE_COLS]), ""]
    thin = s[(s.period == "full") & (s.strategy != BUY_AND_HOLD) & (s.trades < 30)]
    lines += ["## 10. Risks and limitations", "",
              "- Corporate actions: " + ("applied from the actions file." if a.adjusted and a.adjustments_applied
                                         else "not applied yet. Results are distorted by bonus/split events."),
              "- Survivorship bias: index constituents are today's lists, so past performance excludes stocks that dropped out.",
              "- Data source: NSE bhavcopy is official but has no intraday data. Some files are served in "
              "different layouts across years, which the parser handles.",
              "- Costs are assumptions, not your broker's actual charges.",
              "- Small samples: " + (", ".join(f"{r.strategy} ({int(r.trades)} trades)" for _, r in thin.iterrows())
                                    if len(thin) else "none flagged") +
              " have fewer than 30 trades, so their results are statistically weak.",
              "- Past results do not predict future performance. No live trading is supported.", "",
              "## 11. Pine Script", "",
              f"See the Pine Script for these rules in `reports/{a.symbol}_pine_*.pine` (Phase 6)."]
    return "\n".join(lines) + "\n"
