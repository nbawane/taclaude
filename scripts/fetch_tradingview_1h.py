"""Fetch hourly bars from TradingView for the Nifty 500 into DuckDB table tradingview_prices_1h.
Resumable: progress is kept per symbol in table tv_fetch_progress and each symbol is committed on its own,
so a crash, Ctrl-C or reboot loses at most the symbol in flight. Re-running skips finished symbols.

  .venv/bin/python scripts/fetch_tradingview_1h.py                  # fetch everything still pending
  .venv/bin/python scripts/fetch_tradingview_1h.py --retry-failed   # also retry failed symbols
  .venv/bin/python scripts/fetch_tradingview_1h.py --refresh        # re-fetch finished symbols (top up to now)
  .venv/bin/python scripts/fetch_tradingview_1h.py --status         # counts, coverage, ETA, recent errors
  .venv/bin/python scripts/fetch_tradingview_1h.py --watch          # --status every 10 s
  Options: --limit N (first N symbols), --symbols A,B, --years 5, --sleep 1.5

Credentials (optional, more history with a logged-in plan): env TV_USERNAME and TV_PASSWORD.
Monitoring: log logs/tv_fetch.log and heartbeat logs/tv_fetch_heartbeat.json (updated after every symbol).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from niftyta.data.store import DEFAULT_DB, PriceStore  # noqa: E402

LOG_DIR = ROOT / "logs"
HEARTBEAT = LOG_DIR / "tv_fetch_heartbeat.json"
BARS_PER_YEAR = 1800            # ~7 hourly NSE bars x ~250 days, used to size the request
MAX_CONSECUTIVE_FAILURES = 8    # stop instead of hammering TradingView
log = logging.getLogger("tv_fetch")


# ---------- data sources ----------
class TvDatafeedSource:
    """Real source: tvdatafeed (unofficial TradingView websocket client). Needs `pip install` of tvdatafeed."""

    def __init__(self) -> None:
        from tvDatafeed import Interval, TvDatafeed  # imported late so --status works without it
        user, pw = os.environ.get("TV_USERNAME"), os.environ.get("TV_PASSWORD")
        self.tv = TvDatafeed(user, pw) if user and pw else TvDatafeed()
        self.interval = Interval.in_1_hour

    def fetch(self, tv_symbol: str, n_bars: int) -> pd.DataFrame:
        df = self.tv.get_hist(tv_symbol, "NSE", interval=self.interval, n_bars=n_bars)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.reset_index().rename(columns={"datetime": "ts"})
        return df[["ts", "open", "high", "low", "close", "volume"]]


class FakeSource:
    """Synthetic bars for testing the resume and monitoring logic. Never use with the real database."""

    def __init__(self, fail: set[str] | None = None) -> None:
        self.fail = fail or set()

    def fetch(self, tv_symbol: str, n_bars: int) -> pd.DataFrame:
        if tv_symbol in self.fail:
            raise RuntimeError("simulated feed error")
        end = pd.Timestamp.now().floor("h")
        ts = pd.date_range(end=end, periods=min(n_bars, 500), freq="h")
        px = 100 + pd.Series(range(len(ts)), dtype=float).values * 0.01
        return pd.DataFrame({"ts": ts, "open": px, "high": px + 1, "low": px - 1, "close": px + 0.5, "volume": 1000.0})


# ---------- helpers ----------
def to_tv_symbol(sym: str) -> str:
    """NSE symbol -> TradingView ticker (TradingView uses underscores, e.g. M&M -> M_M). Wrong guesses
    show up as 'no data' failures in --status."""
    return sym.replace("&", "_").replace("-", "_")


def clean(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"])
    if df["ts"].dt.tz is not None:
        df["ts"] = df["ts"].dt.tz_convert("UTC").dt.tz_localize(None)
    else:  # tvdatafeed returns exchange-local (IST) naive times
        df["ts"] = df["ts"] - pd.Timedelta(hours=5, minutes=30)
    df = df.drop_duplicates("ts").sort_values("ts")
    ok = (df[["open", "high", "low", "close"]] > 0).all(axis=1) & (df["high"] >= df["low"])
    if (~ok).any():
        log.warning("%s: dropped %d invalid bars", symbol, int((~ok).sum()))
    df = df[ok]
    df.insert(0, "symbol", symbol)
    return df


def set_progress(store: PriceStore, symbol: str, tv: str, status: str, bars=None, first=None, last=None,
                 error=None, bump=False) -> None:
    store.conn.execute(
        "INSERT INTO tv_fetch_progress (symbol, tv_symbol, status, bars, first_ts, last_ts, attempts, error, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, now()::TIMESTAMP) "
        "ON CONFLICT (symbol) DO UPDATE SET tv_symbol=excluded.tv_symbol, status=excluded.status, "
        "bars=COALESCE(excluded.bars, tv_fetch_progress.bars), first_ts=COALESCE(excluded.first_ts, tv_fetch_progress.first_ts), "
        "last_ts=COALESCE(excluded.last_ts, tv_fetch_progress.last_ts), "
        "attempts=tv_fetch_progress.attempts + ?, error=excluded.error, updated_at=excluded.updated_at",
        [symbol, tv, status, bars, first, last, 1 if bump else 0, error, 1 if bump else 0])


def write_heartbeat(**kw) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    kw["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    HEARTBEAT.write_text(json.dumps(kw, indent=1))


def status(store: PriceStore, years: int) -> None:
    c = store.conn
    counts = dict(c.execute("SELECT status, count(*) FROM tv_fetch_progress GROUP BY 1").fetchall())
    total = len(universe_symbols())
    done, failed = counts.get("done", 0), counts.get("failed", 0)
    print(f"symbols: {total} in universe | done {done} | failed {failed} | pending {total - done - failed}")
    r = c.execute("SELECT count(*), min(ts), max(ts) FROM tradingview_prices_1h").fetchone()
    print(f"bars stored: {r[0]:,}  from {r[1]} to {r[2]} (UTC)")
    target = datetime.now() - timedelta(days=365 * years)
    short = c.execute("SELECT count(*) FROM tv_fetch_progress WHERE status='done' AND first_ts > ?", [target]).fetchone()[0]
    print(f"coverage: {short} done symbols start later than {years}y ago (feed depth limit or recent listing)")
    if HEARTBEAT.exists():
        hb = json.loads(HEARTBEAT.read_text())
        print(f"last heartbeat {hb.get('updated_at')} | rate {hb.get('rate_per_min')}/min | ETA {hb.get('eta_min')} min "
              f"| last {hb.get('last_symbol')}")
    errs = c.execute("SELECT symbol, tv_symbol, attempts, error FROM tv_fetch_progress WHERE status='failed' "
                     "ORDER BY updated_at DESC LIMIT 10").fetchall()
    for e in errs:
        print(f"  FAILED {e[0]} (tv:{e[1]}, attempts {e[2]}): {e[3]}")


def universe_symbols() -> list[str]:
    df = pd.read_csv(ROOT / "data" / "reference" / "ind_nifty500list.csv")
    return sorted(df["Symbol"].str.strip().unique())


# ---------- main loop ----------
def run(args) -> int:
    store = PriceStore(args.db)
    if args.status or args.watch:
        while True:
            status(store, args.years)
            if not args.watch:
                break
            time.sleep(10)
            print("-" * 60)
        return 0

    symbols = args.symbols.split(",") if args.symbols else universe_symbols()
    symbols = symbols[: args.limit] if args.limit else symbols
    state = {r[0]: r[1] for r in store.conn.execute("SELECT symbol, status FROM tv_fetch_progress").fetchall()}
    todo = [s for s in symbols if state.get(s) in (None, "pending")
            or (state.get(s) == "failed" and args.retry_failed) or (state.get(s) == "done" and args.refresh)]
    log.info("universe %d | to fetch %d | skipping %d already done/failed", len(symbols), len(todo), len(symbols) - len(todo))

    source = FakeSource(set(args.fake_fail.split(","))) if args.fake else TvDatafeedSource()
    stop = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))

    n_bars = args.years * BARS_PER_YEAR
    t0, ok_n, fail_n, consecutive = time.time(), 0, 0, 0
    for i, sym in enumerate(todo, 1):
        if stop["flag"]:
            log.info("stop requested: exiting cleanly after %d symbols; re-run to resume", i - 1)
            break
        tv = to_tv_symbol(sym)
        err = None
        for attempt in range(1, args.attempts + 1):
            try:
                raw = source.fetch(tv, n_bars)
                if raw.empty:
                    raise RuntimeError("no data returned (check the TradingView ticker)")
                df = clean(raw, sym)
                store.upsert_tv_1h(df)
                set_progress(store, sym, tv, "done", len(df), df["ts"].min().to_pydatetime(),
                             df["ts"].max().to_pydatetime(), bump=True)
                log.info("[%d/%d] %s ok: %d bars %s -> %s", i, len(todo), sym, len(df), df["ts"].min().date(), df["ts"].max().date())
                err = None
                break
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
                log.warning("[%d/%d] %s attempt %d/%d failed: %s", i, len(todo), sym, attempt, args.attempts, err)
                time.sleep(min(60, 2 ** attempt * args.sleep))
        if err is None:
            ok_n, consecutive = ok_n + 1, 0
        else:
            fail_n, consecutive = fail_n + 1, consecutive + 1
            set_progress(store, sym, tv, "failed", error=err, bump=True)
        elapsed = time.time() - t0
        rate = (ok_n + fail_n) / elapsed * 60 if elapsed else 0
        write_heartbeat(done_this_run=ok_n, failed_this_run=fail_n, total_this_run=len(todo), last_symbol=sym,
                        rate_per_min=round(rate, 1), eta_min=round((len(todo) - i) / rate, 1) if rate else None)
        if consecutive >= MAX_CONSECUTIVE_FAILURES:
            log.error("%d symbols failed in a row: stopping (feed down, login expired or rate limited). Re-run to resume.", consecutive)
            return 2
        time.sleep(args.sleep)
    log.info("run finished: %d ok, %d failed", ok_n, fail_n)
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--symbols")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--sleep", type=float, default=1.5, help="seconds between symbols")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--fake", action="store_true", help="synthetic data, for testing only (needs a non-default --db)")
    ap.add_argument("--fake-fail", default="")
    args = ap.parse_args()
    if args.fake and Path(args.db).resolve() == DEFAULT_DB.resolve():
        sys.exit("--fake must not write to the real database; pass --db <test file>")
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), RotatingFileHandler(LOG_DIR / "tv_fetch.log", maxBytes=2_000_000, backupCount=3)])
    sys.exit(run(args))


if __name__ == "__main__":
    main()
