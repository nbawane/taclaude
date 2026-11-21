"""Phase 7: run the system from a plain-English prompt.

Examples (run from the project folder):
  .venv/bin/python scripts/niftyta.py "Analyze RELIANCE on the daily timeframe. Apply RSI 14, EMA 9/21 and Bollinger Bands. Backtest all three strategies for five years. Compare performance. Generate a Pine Script for the best strategy."
  .venv/bin/python scripts/niftyta.py "Find the best-performing strategy among the Nifty 50 stocks, weekly"
  .venv/bin/python scripts/niftyta.py "Test the EMA crossover strategy on daily, weekly and monthly timeframes for TCS"
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from niftyta.backtest.runner import BUY_AND_HOLD  # noqa: E402
from niftyta.data.store import PriceStore  # noqa: E402
from niftyta.nl.parse import parse_prompt  # noqa: E402
from niftyta.pine.generator import write as write_pine  # noqa: E402
from niftyta.pipeline.run import analyse  # noqa: E402
from niftyta.reporting.report import build_report  # noqa: E402
from niftyta.indicators.core import load_params  # noqa: E402

MIN_OOS_TRADES = 5  # rankings below this are statistically meaningless

STRATEGY_LABEL = {"rsi": "RSI(14) 30/70", "ema_cross": "EMA 9/21 cross", "bbands": "Bollinger 20,2"}


def best_strategy(summary: pd.DataFrame, keys: list[str]) -> str | None:
    """Pick by out-of-sample Sharpe, the measure least likely to reward one lucky period."""
    oos = summary[(summary.period == "out_of_sample") & (summary.strategy != BUY_AND_HOLD)]
    oos = oos[oos.strategy.isin([STRATEGY_LABEL[k] for k in keys])].dropna(subset=["sharpe"])
    return None if oos.empty else oos.sort_values("sharpe", ascending=False).iloc[0].strategy


def main() -> None:
    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        sys.exit(__doc__)
    store = PriceStore()
    known = {r[0] for r in store.conn.execute("SELECT DISTINCT symbol FROM prices_daily").fetchall()}
    store.close()
    req = parse_prompt(prompt, known)

    print("Understood:")
    print(f"  stocks:      {', '.join(req.symbols) if req.symbols else '-'}")
    print(f"  timeframes:  {', '.join(req.timeframes)}")
    print(f"  strategies:  {', '.join(STRATEGY_LABEL[s] for s in req.strategies)}")
    print(f"  years:       {req.years}")
    print(f"  Pine Script: {'yes' if req.pine else 'no'}")
    for n in req.unsupported:
        print(f"  NOT SUPPORTED YET (ignored): {n}")
    for n in req.notes:
        print(f"  note: {n}")
    if not req.symbols:
        sys.exit(1)

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    rows = []
    for sym in req.symbols:
        for tf in req.timeframes:
            try:
                a = analyse(sym, tf, years=req.years)
            except LookupError as e:
                print(f"  skip {sym} {tf}: {e}")
                continue
            build_report(a, reports)  # writes the 11-section Markdown report
            full = a.summary[a.summary.period == "full"]
            oos = a.summary[a.summary.period == "out_of_sample"]
            for _, r in oos.iterrows():
                rows.append({"symbol": sym, "timeframe": tf, "strategy": r.strategy,
                             "oos_return": r.total_return, "oos_sharpe": r.sharpe,
                             "oos_trades": int(r.trades), "adjusted": a.adjusted and a.adjustments_applied > 0})
            if req.pine and sym == req.symbols[0] and tf == req.timeframes[0]:
                best = best_strategy(a.summary, req.strategies)
                key = next((k for k, v in STRATEGY_LABEL.items() if v == best), None)
                if key:
                    pine, notes = write_pine(key, sym, tf, load_params(), reports / "pine")
                    print(f"  Pine Script for best out-of-sample strategy ({best}): {pine}")
                    print(f"  Pine notes: {notes}")
                else:
                    print("  Pine Script: no strategy had enough data to pick a best one.")
            print(f"  report: reports/{sym}_{tf}_REPORT.md")

    if rows:
        table = pd.DataFrame(rows)
        table = table[table.strategy.isin([STRATEGY_LABEL[k] for k in req.strategies])]
        enough = table[table.oos_trades >= MIN_OOS_TRADES]
        print(f"\n{len(table) - len(enough)} of {len(table)} results have fewer than {MIN_OOS_TRADES} "
              "out-of-sample trades and are left out of the ranking.")
        ranked = enough.sort_values("oos_sharpe", ascending=False)
        if ranked.empty:
            print("No result has enough trades to rank. Try a longer period or a different timeframe.")
            return
        out = reports / "ranking_latest.csv"
        ranked.to_csv(out, index=False, float_format="%.4f")
        print("\nOut-of-sample ranking (by Sharpe; top 15 shown):")
        with pd.option_context("display.width", 200):
            print(ranked.head(15).round(3).to_string(index=False))
        print(f"\nfull ranking: {out}")
        if not all(ranked.adjusted):
            print("\nWARNING: prices are not adjusted for corporate actions; this ranking is provisional.")


if __name__ == "__main__":
    main()
