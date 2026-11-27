"""Propose split/bonus factors for review: Yahoo's split events, checked against raw NSE prices.

Usage: .venv/bin/python scripts/propose_adjustments.py [--refresh]
Writes data/reference/corporate_actions_proposed.csv (every event with its evidence),
corporate_actions_unexplained.csv (large NSE moves with no verified event) and
reports/corporate_actions_review.html. It does NOT change corporate_actions.csv or the database.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402

from niftyta.data.ca_reconcile import judge  # noqa: E402

REF = ROOT / "data" / "reference"
SPLITS = REF / "yfinance_splits.csv"


def fetch_splits(symbols: list[str], refresh: bool) -> pd.DataFrame:
    """Cached and resumable: symbols already asked (including those with no split) are skipped."""
    done = pd.read_csv(SPLITS) if SPLITS.exists() and not refresh else pd.DataFrame(columns=["symbol", "date", "ratio"])
    asked, rows = set(done.symbol), done.to_dict("records")
    failed = []
    yf.config.debug.hide_exceptions = False  # surface download errors so they can be retried
    for i, s in enumerate(x for x in symbols if x not in asked):
        try:
            act = yf.Ticker(f"{s}.NS").history(period="max", auto_adjust=False, actions=True)
            sp = act.loc[act["Stock Splits"] > 0, "Stock Splits"]
            rows += [{"symbol": s, "date": d.date().isoformat(), "ratio": float(r)} for d, r in sp.items()] or \
                    [{"symbol": s, "date": None, "ratio": None}]
        except Exception as e:  # report and carry on; a rerun retries
            failed.append(f"{s}: {e}")
        if i % 25 == 24:
            pd.DataFrame(rows).to_csv(SPLITS, index=False)
            print(f"  {i + 1} fetched", flush=True)
        time.sleep(0.2)
    out = pd.DataFrame(rows)
    out.to_csv(SPLITS, index=False)
    if failed:
        print(f"{len(failed)} symbol(s) failed (rerun to retry):", *failed, sep="\n  ")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="download all split events again")
    args = ap.parse_args()
    symbols = pd.read_csv(REF / "yfinance_symbols.csv").symbol.tolist()
    splits = fetch_splits(symbols, args.refresh).dropna(subset=["date"])

    con = duckdb.connect(str(ROOT / "data" / "niftyta.duckdb"), read_only=True)
    con.register("u", pd.DataFrame({"symbol": symbols}))
    load = lambda t: {s: g.set_index(pd.DatetimeIndex(g.date))["close"] for s, g in con.execute(
        f"select symbol, date, close from {t} join u using(symbol) order by symbol, date").df().groupby("symbol")}
    nse, yah = load("prices_daily"), load("yfinance_prices_daily")
    con.close()

    rows = []
    for e in splits.itertuples():
        if e.symbol not in nse:
            continue
        factor = 1 / e.ratio
        ev = judge(nse[e.symbol], yah.get(e.symbol), pd.Timestamp(e.date), factor)
        if ev["status"] != "outside_data":
            rows.append({"symbol": e.symbol, "ex_date": ev["ex_date"].date(), "factor": round(ev["factor"], 6), "listed_factor": round(factor, 6),
                         "yahoo_date": e.date, "nse_ratio": round(ev["nse_ratio"], 4),
                         "step_factor": round(ev["step_factor"], 4), "status": ev["status"]})
    prop = pd.DataFrame(rows).drop_duplicates(["symbol", "ex_date", "factor"]).sort_values(["symbol", "ex_date"])
    prop.to_csv(REF / "corporate_actions_proposed.csv", index=False)

    ok = prop[prop.status.str.startswith("verified")]
    odd = []
    for s, c in nse.items():
        r = c / c.shift(1)
        for d, v in r[(r < 0.65) | (r > 1.5)].items():
            if not ((ok.symbol == s) & (pd.to_datetime(ok.ex_date) == d)).any():
                odd.append({"symbol": s, "date": d.date(), "prev_close": round(c.shift(1)[d], 2),
                            "close": round(c[d], 2), "ratio": round(v, 4),
                            "days_since_prev_bar": (d - c.index[c.index.get_loc(d) - 1]).days})
    odd = pd.DataFrame(odd).sort_values(["symbol", "date"])
    odd.to_csv(REF / "corporate_actions_unexplained.csv", index=False)

    # effect: how often NSE agrees with Yahoo (within 1%) before and after applying verified factors
    total = before = after = 0
    for s, c in nse.items():
        if s not in yah:
            continue
        adj = c.copy()
        for a in ok[ok.symbol == s].itertuples():
            adj.loc[adj.index < pd.Timestamp(a.ex_date)] *= a.factor
        j = pd.concat([c, adj, yah[s]], axis=1, join="inner")
        total += len(j)
        before += int(((j.iloc[:, 0] / j.iloc[:, 2] - 1).abs() < 0.01).sum())
        after += int(((j.iloc[:, 1] / j.iloc[:, 2] - 1).abs() < 0.01).sum())

    write_review(ROOT / "reports" / "corporate_actions_review.html", prop, odd, nse)
    print("events by status:", prop.status.value_counts().to_dict())
    print(f"symbols with a verified event: {ok.symbol.nunique()}")
    print(f"large NSE moves left unexplained: {len(odd)} in {odd.symbol.nunique()} symbols")
    print(f"agreement with Yahoo within 1%: raw {before / total:.2%} -> adjusted {after / total:.2%} of {total} bars")


def write_review(path: Path, prop: pd.DataFrame, odd: pd.DataFrame, nse: dict) -> None:
    items = [{"s": r.symbol, "d": str(r.ex_date), "f": r.factor, "k": r.status} for r in prop.itertuples()]
    items += [{"s": r.symbol, "d": str(r.date), "f": None, "k": "unexplained"} for r in odd.itertuples()]
    for it in items:
        c, d = nse[it["s"]], pd.Timestamp(it["d"])
        i = c.index.searchsorted(d)
        w = c.iloc[max(i - 60, 0):i + 60]
        it["x"] = [t.strftime("%Y-%m-%d") for t in w.index]
        it["raw"] = [round(float(v), 2) for v in w]
        it["adj"] = None if it["f"] is None else [round(float(v) * (it["f"] if t < d else 1), 2) for t, v in w.items()]
    path.parent.mkdir(exist_ok=True)
    path.write_text(PAGE.replace("__DATA__", json.dumps(items, allow_nan=False)))


PAGE = """<!doctype html><meta charset="utf-8"><title>Corporate action review</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>body{font:14px system-ui;margin:16px}select,input{font:inherit;padding:4px}#c{height:560px}</style>
<h3>Split / bonus review: raw NSE close vs adjusted</h3>
<label>Status <select id="k"></select></label> <label>Symbol <input id="q" size="12"></label>
<label>Event <select id="e"></select></label> <button id="p">Previous</button> <button id="n">Next</button>
<div id="c"></div>
<script>
const D=__DATA__, $=i=>document.getElementById(i);
["check","no_evidence","unexplained","verified_combined","verified"].forEach(k=>$("k").add(new Option(k+" ("+D.filter(x=>x.k==k).length+")",k)));
function list(){const q=$("q").value.toUpperCase();$("e").length=0;
 D.forEach((x,i)=>{if(x.k==$("k").value&&x.s.includes(q))$("e").add(new Option(x.s+"  "+x.d+(x.f?"  x"+x.f:""),i))});draw()}
function draw(){const x=D[$("e").value];if(!x){Plotly.purge("c");return}
 const t=[{x:x.x,y:x.raw,name:"raw NSE",line:{color:"#888"}}];
 if(x.adj)t.push({x:x.x,y:x.adj,name:"adjusted",line:{color:"#1f77b4"}});
 Plotly.newPlot("c",t,{title:x.s+" "+x.d+" ("+x.k+")",hovermode:"x unified",
  shapes:[{type:"line",x0:x.d,x1:x.d,y0:0,y1:1,yref:"paper",line:{dash:"dot"}}]},{responsive:true})}
$("k").onchange=list;$("q").oninput=list;$("e").onchange=draw;
for(const [b,s] of [["p",-1],["n",1]])$(b).onclick=()=>{const e=$("e");
 if(e.length){e.selectedIndex=(e.selectedIndex+s+e.length)%e.length;draw()}};
$("k").value="check";list();
</script>"""


if __name__ == "__main__":
    main()
