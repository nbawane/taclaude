"""Phase 6: write Pine Script v6 strategy files for the three rule sets.
Usage: .venv/bin/python scripts/pine.py RELIANCE --timeframe 1D
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.data.store import PriceStore  # noqa: E402
from niftyta.indicators.core import load_params  # noqa: E402
from niftyta.pine.generator import write, write_gfs  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="RELIANCE")
    ap.add_argument("--gfs", action="store_true", help="write only the GFS strategy (run on the Son timeframe)")
    ap.add_argument("--timeframe", default="1D", choices=["1D", "1W", "1M"])
    args = ap.parse_args()
    from datetime import date, timedelta
    store = PriceStore()
    end = date.today() + timedelta(days=1)
    last = store.load(args.symbol.upper(), end - timedelta(days=10), end)
    store.close()
    price = float(last["close"].iloc[-1]) if len(last) else 1000.0
    out = ROOT / "reports" / "pine"
    if args.gfs:
        print(write_gfs(args.symbol.upper(), out))
        return
    for key in ("rsi", "ema_cross", "bbands"):
        pine, notes = write(key, args.symbol.upper(), args.timeframe, load_params(), out, price)
        print(f"{pine}\n{notes}")


if __name__ == "__main__":
    main()
