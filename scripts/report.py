"""Phase 5: write the 11-section report for a stock and timeframe.
Usage: .venv/bin/python scripts/report.py RELIANCE --timeframe 1D
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.pipeline.run import analyse  # noqa: E402
from niftyta.reporting.report import build_report  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="RELIANCE")
    ap.add_argument("--timeframe", default="1D", choices=["1D", "1W", "1M"])
    args = ap.parse_args()
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    a = analyse(args.symbol, args.timeframe)
    md = build_report(a, reports)
    path = reports / f"{a.symbol}_{a.timeframe}_REPORT.md"
    path.write_text(md)
    print(f"report: {path}")


if __name__ == "__main__":
    main()
