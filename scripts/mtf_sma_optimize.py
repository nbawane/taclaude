"""Improve the multi-timeframe SMA strategy in a shared portfolio, one stage at a time.

Settings are chosen on BUILD, confirmed on CONFIRM, and FINAL is run only for the starting and chosen
settings. A change is kept only if return / max drawdown improves in BOTH build and confirm and the
drawdown stays within MAX_DD in both. Every variant tried is logged.

Usage: .venv/bin/python scripts/mtf_sma_optimize.py
Output: reports/mtf_sma_opt/ and the mtf_sma_portfolio block in config/strategies.yaml
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, replace
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.backtest.portfolio import PortfolioConfig  # noqa: E402
from niftyta.data.store import DEFAULT_DB  # noqa: E402
from niftyta.pipeline.mtf_sma_portfolio import (Variant, add_market, market_uptrend, prepare,  # noqa: E402
                                                run_variant)

WINDOWS = {"build": ("2018-07-01", "2022-12-31"), "confirm": ("2023-01-01", "2024-12-31"),
           "final": ("2025-01-01", None)}
MAX_DD = 0.20
OUT = ROOT / "reports" / "mtf_sma_opt"


def load():
    with duckdb.connect(str(DEFAULT_DB), read_only=True) as conn:
        px = conn.execute("SELECT * FROM yfinance_prices_daily ORDER BY symbol, date").df()
        idx = conn.execute("SELECT date, close FROM index_daily WHERE index_name = 'Nifty 500' ORDER BY date").df()
    px["date"], idx["date"] = pd.to_datetime(px["date"]), pd.to_datetime(idx["date"])
    cfg = yaml.safe_load(open(ROOT / "config" / "strategies.yaml"))["mtf_sma"]
    data = {s: prepare(d.set_index("date").dropna(subset=["open", "high", "low", "close", "adj_close"]),
                       cfg["period"], cfg["confirm_days"]) for s, d in px.groupby("symbol")}
    index = idx.set_index("date")["close"]
    add_market(data, market_uptrend(index))
    return data, index


def label(v: Variant) -> str:
    c = v.cfg
    stop = {"atr": f"{c.stop_atr:g}xATR stop", "swing": "10-day low stop", "none": "no stop"}[c.stop]
    exit_ = {"sma": "daily SMA exit", "weekly": "weekly SMA exit", "target": f"{c.target_r:g}R target",
             "half_trail": f"half at {c.target_r:g}R, trail {c.trail_atr:g}xATR",
             "atr_trail": f"{c.trail_atr:g}xATR trail"}[c.exit]
    size = f"risk {c.risk_pct:.1%}, {c.max_positions} positions, max {c.max_position_pct:.0%}"
    return f"{stop} | {exit_} | {size} | filters: {', '.join(v.filters) or 'none'}"


def stages(cur: Variant):
    c = cur.cfg
    return {
        "2 stoploss": [replace(cur, cfg=replace(c, stop="atr", stop_atr=k)) for k in (1.5, 2.0, 3.0)]
                      + [replace(cur, cfg=replace(c, stop="swing"))],
        "3 exit": [replace(cur, cfg=replace(c, exit=e, **kw)) for e, kw in (
            ("sma", {}), ("target", {"target_r": 2.0}), ("target", {"target_r": 3.0}),
            ("half_trail", {"target_r": 2.0}), ("atr_trail", {"trail_atr": 2.0}),
            ("atr_trail", {"trail_atr": 3.0}), ("atr_trail", {"trail_atr": 4.0}), ("weekly", {}))],
        "4 filter": [replace(cur, filters=cur.filters + (f,)) for f in
                     ("market", "liquid10", "liquid50", "not_extended", "weekly_rising") if f not in cur.filters],
        "5 sizing": [replace(cur, cfg=replace(c, risk_pct=r, max_positions=n, max_position_pct=p))
                     for r in (0.005, 0.01, 0.015) for n, p in ((4, .25), (5, .25), (8, .15))],
    }


def main() -> None:
    data, index = load()
    log, cache = [], {}

    def evaluate(stage: str, v: Variant) -> dict:
        if v not in cache:
            cache[v] = {w: run_variant(data, v, *WINDOWS[w])[1] for w in ("build", "confirm")}
        m = cache[v]
        for w in m:
            log.append({"stage": stage, "variant": label(v), "window": w, **m[w]})
        return m

    ok = lambda m: all(abs(m[w]["max_drawdown"]) <= MAX_DD for w in m)

    def better(new: dict, old: dict) -> bool:
        return ok(new) and (not ok(old) or all(new[w]["calmar"] > old[w]["calmar"] for w in new))

    start = Variant()
    current, history = start, []
    base = evaluate("1 baseline", current)
    history.append({"step": "1 baseline", "chosen": label(current), "changed": False,
                    **{f"{w}_{k}": base[w][k] for w in base for k in ("cagr", "max_drawdown")}})
    for name in ("2 stoploss", "3 exit", "4 filter", "5 sizing"):
        rounds = 4 if name == "4 filter" else 1   # filters may stack, one at a time
        for _ in range(rounds):
            old = evaluate(name, current)
            passing = [(v, m) for v in stages(current)[name] if v != current
                       for m in [evaluate(name, v)] if better(m, old)]
            if passing:
                current, m = max(passing, key=lambda p: p[1]["build"]["calmar"])
            m = cache[current]
            history.append({"step": name, "chosen": label(current), "changed": bool(passing),
                            **{f"{w}_{k}": m[w][k] for w in m for k in ("cagr", "max_drawdown")}})
            print(f"{name}: {'changed' if passing else 'kept'} -> {label(current)}", flush=True)
            if not passing:
                break

    # one look at the final window, plus the whole period, for the starting and chosen settings
    summary, equity = [], {}
    names = {"Starting setup": start, "Improved setup": current}
    spans = {**WINDOWS, "whole period": (WINDOWS["build"][0], None)}
    trades = None
    for w, (a, b) in spans.items():
        for name, v in names.items():
            res, m = run_variant(data, v, a, b)
            summary.append({"window": w, "setup": name, **m})
            if w == "whole period":
                equity[name] = res.equity
                if name == "Improved setup":
                    trades = res.trades
        i = index.loc[a:b]
        years = (i.index[-1] - i.index[0]).days / 365.25
        summary.append({"window": w, "setup": "Nifty 500 index", "cagr": (i.iloc[-1] / i.iloc[0]) ** (1 / years) - 1,
                        "total_return": i.iloc[-1] / i.iloc[0] - 1, "max_drawdown": (i / i.cummax() - 1).min()})
    equity["Nifty 500 index"] = index.reindex(equity["Improved setup"].index, method="ffill")

    # how much does luck matter? same rules, competing signals picked at random
    luck = []
    for seed in range(30):
        rng = np.random.default_rng(seed)
        shuffled = {s: d.assign(score=rng.random(len(d))) for s, d in data.items()}
        for w in ("build", "confirm", "final"):
            m = run_variant(shuffled, current, *WINDOWS[w])[1]
            luck.append({"seed": seed, "window": w, "cagr": m["cagr"], "max_drawdown": m["max_drawdown"]})

    # neighbours of the chosen settings: a good setting should not depend on one exact number
    near = []
    c = current.cfg
    changes = [("stop_atr", c.stop_atr * f) for f in (.75, 1.25)] + [("trail_atr", c.trail_atr * f) for f in (.75, 1.25)] \
        + [("risk_pct", c.risk_pct * f) for f in (.75, 1.25)] + [("max_positions", c.max_positions + d) for d in (-1, 1)]
    for key, value in changes:
        if (key == "stop_atr" and c.stop != "atr") or (key == "trail_atr" and c.exit not in ("atr_trail", "half_trail")):
            continue
        v = replace(current, cfg=replace(c, **{key: value}))
        for w in ("build", "confirm"):
            m = run_variant(data, v, *WINDOWS[w])[1]
            near.append({"changed": f"{key} = {value:g}", "window": w, "cagr": m["cagr"],
                         "max_drawdown": m["max_drawdown"]})

    OUT.mkdir(parents=True, exist_ok=True)
    for fname, frame in (("experiments", pd.DataFrame(log).drop_duplicates(["stage", "variant", "window"])),
                         ("steps", pd.DataFrame(history)), ("summary", pd.DataFrame(summary)),
                         ("luck", pd.DataFrame(luck)), ("neighbours", pd.DataFrame(near)), ("trades", trades)):
        frame.to_csv(OUT / f"{fname}.csv", index=False, float_format="%.5f")
    pd.DataFrame(equity).to_csv(OUT / "equity.csv", index_label="date", float_format="%.3f")
    (OUT / "chosen.json").write_text(json.dumps({**asdict(current.cfg), "filters": list(current.filters)}, indent=2))

    path = ROOT / "config" / "strategies.yaml"
    text = re.sub(r"\n# Chosen by scripts/mtf_sma_optimize\.py[^\n]*\nmtf_sma_portfolio:\n(?:  .*\n)*", "", path.read_text())
    block = yaml.safe_dump({"mtf_sma_portfolio": {**asdict(current.cfg), "filters": list(current.filters)}},
                           sort_keys=False)
    path.write_text(text.rstrip("\n") + f"\n\n# Chosen by scripts/mtf_sma_optimize.py (rewritten on each run)\n{block}")

    pd.set_option("display.width", 220)
    show = ["window", "setup", "cagr", "max_drawdown", "calmar", "trades", "win_rate", "profit_factor",
            "avg_win", "avg_loss", "exposure"]
    print(pd.DataFrame(summary)[show].round(3).to_string(index=False))
    print("\nrandom ranking, 30 runs:\n", pd.DataFrame(luck).groupby("window")[["cagr", "max_drawdown"]]
          .quantile([0, .5, 1]).round(3).to_string())
    print("\nneighbours:\n", pd.DataFrame(near).round(3).to_string(index=False))
    ex = pd.DataFrame(log).drop_duplicates(["stage", "variant", "window"])
    print(f"\nvariants tried: {ex.variant.nunique()}")
    print(ex.pivot_table(index=["stage", "variant"], columns="window", values=["cagr", "max_drawdown"])
          .round(3).to_string())


if __name__ == "__main__":
    main()
