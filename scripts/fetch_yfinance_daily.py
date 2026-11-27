"""Download daily bars from Yahoo Finance (yfinance) for the Nifty 500 into DuckDB table yfinance_prices_daily.
Resumable: each batch is committed on its own and each symbol's result is kept in yf_fetch_progress.
Re-running skips finished symbols.

  .venv/bin/python scripts/fetch_yfinance_daily.py                 # last 10 years, all pending symbols
  .venv/bin/python scripts/fetch_yfinance_daily.py --retry-failed
  .venv/bin/python scripts/fetch_yfinance_daily.py --refresh       # re-download finished symbols up to today
  .venv/bin/python scripts/fetch_yfinance_daily.py --status
  Options: --years 10 --limit N --symbols A,B --batch 20 --sleep 2
Log: logs/yf_fetch.log
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import date, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.data.store import PriceStore  # noqa: E402

LOG_DIR = ROOT / "logs"
log = logging.getLogger("yf_fetch")


def universe_symbols() -> list[str]:
    df = pd.read_csv(ROOT / "data" / "reference" / "ind_nifty500list.csv")
    return sorted(df["Symbol"].str.strip().unique())


def download(symbols: list[str], start: date, end: date) -> dict[str, pd.DataFrame]:
    import yfinance as yf
    tickers = [f"{s}.NS" for s in symbols]
    raw = yf.download(tickers, start=start.isoformat(), end=end.isoformat(), interval="1d", auto_adjust=False,
                      group_by="ticker", progress=False, threads=True)
    out: dict[str, pd.DataFrame] = {}
    for s, t in zip(symbols, tickers):
        try:
            df = raw[t] if len(symbols) > 1 else raw
        except KeyError:
            continue
        df = df.dropna(subset=["Close"]).rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close",
                                                         "Adj Close": "adj_close", "Volume": "volume"})
        if df.empty:
            continue
        df = df[["open", "high", "low", "close", "adj_close", "volume"]]
        ok = (df[["open", "high", "low", "close"]] > 0).all(axis=1) & (df["high"] >= df["low"])
        if (~ok).any():
            log.warning("%s: dropped %d invalid bars", s, int((~ok).sum()))
        df = df[ok]
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
        df = df[~df.index.duplicated()]
        df.insert(0, "symbol", s)
        out[s] = df.rename_axis("date").reset_index()
    return out


def save(store: PriceStore, df: pd.DataFrame) -> None:
    store.conn.register("incoming_yf", df)
    try:
        store.conn.execute("INSERT OR REPLACE INTO yfinance_prices_daily SELECT symbol, CAST(date AS DATE), open, high, "
                           "low, close, adj_close, volume FROM incoming_yf")
    finally:
        store.conn.unregister("incoming_yf")


def set_progress(store, sym, status, bars=None, first=None, last=None, error=None) -> None:
    store.conn.execute(
        "INSERT OR REPLACE INTO yf_fetch_progress VALUES (?, ?, ?, ?, ?, "
        "COALESCE((SELECT attempts FROM yf_fetch_progress WHERE symbol=?), 0) + 1, ?, now()::TIMESTAMP)",
        [sym, status, bars, first, last, sym, error])


def status(store: PriceStore, years: int) -> None:
    c = store.conn
    counts = dict(c.execute("SELECT status, count(*) FROM yf_fetch_progress GROUP BY 1").fetchall())
    total = len(universe_symbols())
    done, failed = counts.get("done", 0), counts.get("failed", 0)
    print(f"symbols: {total} in universe | done {done} | failed {failed} | pending {total - done - failed}")
    r = c.execute("SELECT count(*), min(date), max(date) FROM yfinance_prices_daily").fetchone()
    print(f"bars stored: {r[0]:,}  from {r[1]} to {r[2]}")
    cutoff = date.today() - timedelta(days=365 * years - 30)
    short = c.execute("SELECT count(*) FROM yf_fetch_progress WHERE status='done' AND first_date > ?", [cutoff]).fetchone()[0]
    print(f"{short} done symbols start later than {years}y ago (listed more recently)")
    for e in c.execute("SELECT symbol, attempts, error FROM yf_fetch_progress WHERE status='failed' "
                       "ORDER BY updated_at DESC LIMIT 15").fetchall():
        print(f"  FAILED {e[0]} (attempts {e[1]}): {e[2]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--symbols")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--sleep", type=float, default=2.0)
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), RotatingFileHandler(LOG_DIR / "yf_fetch.log", maxBytes=2_000_000, backupCount=3)])
    store = PriceStore()
    if args.status:
        status(store, args.years)
        return 0

    symbols = args.symbols.split(",") if args.symbols else universe_symbols()
    symbols = symbols[: args.limit] if args.limit else symbols
    state = {r[0]: r[1] for r in store.conn.execute("SELECT symbol, status FROM yf_fetch_progress").fetchall()}
    todo = [s for s in symbols if state.get(s) is None or (state[s] == "failed" and args.retry_failed)
            or (state[s] == "done" and args.refresh)]
    log.info("universe %d | to fetch %d | skipping %d", len(symbols), len(todo), len(symbols) - len(todo))
    start, end = date.today() - timedelta(days=365 * args.years + 5), date.today() + timedelta(days=1)

    stop = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    ok_n = fail_n = 0
    for i in range(0, len(todo), args.batch):
        if stop["flag"]:
            log.info("stop requested: exiting cleanly; re-run to resume")
            break
        batch = todo[i:i + args.batch]
        got, err = {}, None
        for attempt in range(1, args.attempts + 1):
            try:
                got = download(batch, start, end)
                err = None
                break
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
                log.warning("batch %d attempt %d/%d failed: %s", i // args.batch + 1, attempt, args.attempts, err)
                time.sleep(min(60, 2 ** attempt * args.sleep))
        for s in batch:
            if s in got:
                df = got[s]
                save(store, df)
                set_progress(store, s, "done", len(df), df["date"].min().date(), df["date"].max().date())
                ok_n += 1
            else:
                set_progress(store, s, "failed", error=err or "no data returned (delisted or wrong Yahoo ticker)")
                fail_n += 1
        log.info("batch %d/%d: %d ok, %d failed so far", i // args.batch + 1, -(-len(todo) // args.batch), ok_n, fail_n)
        time.sleep(args.sleep)
    log.info("run finished: %d ok, %d failed", ok_n, fail_n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
