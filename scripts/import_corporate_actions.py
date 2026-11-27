"""Build data/reference/corporate_actions.csv from NSE exports in data/reference/nse_corporate_actions/.

Usage: .venv/bin/python scripts/import_corporate_actions.py
Only bonus and split events are turned into factors. Dividends, rights and demergers are listed
in data/reference/corporate_actions_log.csv as NOT applied, so the gap stays visible.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from niftyta.data.ca_parse import parse_export  # noqa: E402

SRC = ROOT / "data" / "reference" / "nse_corporate_actions"
OUT = ROOT / "data" / "reference" / "corporate_actions.csv"
LOG = ROOT / "data" / "reference" / "corporate_actions_log.csv"


def main() -> None:
    files = sorted(SRC.glob("*.csv"))
    if not files:
        sys.exit(f"No NSE export files in {SRC}")
    events = pd.concat([parse_export(f) for f in files], ignore_index=True).drop_duplicates(["symbol", "ex_date", "purpose"])
    events["applied"] = events["factor"].notna()
    events.to_csv(LOG, index=False)
    apply = events[events.applied][["symbol", "ex_date", "factor"]].copy()
    apply["ex_date"] = apply["ex_date"].dt.strftime("%Y-%m-%d")
    apply["factor"] = apply["factor"].round(6)
    apply.to_csv(OUT, index=False)
    print(f"{len(files)} file(s), {len(events)} events: {len(apply)} applied as price factors, "
          f"{int((~events.applied).sum())} not applied")
    with pd.option_context("display.width", 200, "display.max_colwidth", 60):
        print(apply.to_string(index=False))
        skipped = events[~events.applied]
        print("\nNOT applied (kind counts):", skipped["kind"].value_counts().to_dict())
        print(skipped[skipped.kind.isin(["demerger", "rights"])][["symbol", "ex_date", "kind", "purpose"]].to_string(index=False))
    print(f"\nwritten: {OUT}\nlog:     {LOG}")


if __name__ == "__main__":
    main()
