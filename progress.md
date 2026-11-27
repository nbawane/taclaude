# NiftyTA progress

Last updated: 2026-11-27. Nothing below is committed to git yet (last commit: `e45188a`).

## Done

### GFS strategy on TradingView
- [x] Pine v6 script: `reports/pine/gfs.pine` (`reports/` does not show in git status)
- [x] Saved in TradingView as "GFS + RSI Divergence" (`USER;185341f0926b408b9fc9bbcc31034d12`)
- [x] Generator support: `src/niftyta/pine/gfs_template.pine`, `generate_gfs()` / `write_gfs()`, `scripts/pine.py SYMBOL --gfs`
- [ ] Generated `RELIANCE_gfs.pine` not yet re-run on TradingView (its commission is 0.0611%, the tested version used 0.1%)

Backtest, NSE:RELIANCE 1D, 1994 to 2026-11-20, 0.1% commission, no slippage:

| Run | Trades | Win rate | Profit factor | Net profit | Max drawdown |
|---|---|---|---|---|---|
| Mode 1, exit A | 30 | 46.7% | 2.06 | +58.4% | 27.4% |
| Mode 1, exit B | 41 (counted per fill) | 53.7% | 1.69 | +38.4% | 20.4% |
| Mode 2, exit A | 1 | 100% | n/a | +6.3% | 1.9% |

Known differences from the Python backtest: costs, pivot ties, alert-low cancel checked at bar close, exits start the bar after the fill.

### RSI strategy on TradingView
- [x] Saved as "NiftyTA RSI(14) 40/60", version 2.0, no slippage (`USER;95a8e322958d49b3893a1c120e3e894a`)
- [x] 30/70 tested on RELIANCE: 19 trades, -8.7% without slippage; 23 trades, -76.0% with the generator's 14-tick slippage
- [ ] 40/60 not backtested

### Yahoo Finance daily data
- [x] Table `yfinance_prices_daily` in `data/niftyta.duckdb`: 1,006,978 bars, 2016-11-21 to 2026-11-20
- [x] 499 of 501 symbols (170 have under 10 years because they listed later)
- [x] Resumable script: `scripts/fetch_yfinance_daily.py` (`--status`, `--refresh`, `--retry-failed`), log `logs/yf_fetch.log`
- [x] Symbol list: `data/reference/yfinance_symbols.csv`
- Failed: DUMMYHEG (placeholder row), BAGMANE (no data for `.NS`; `.BO` has data, not loaded)
- [ ] Not cross-checked against NSE or TradingView prices

## In progress / blocked

### TradingView hourly data (5 years, Nifty 500)
- [x] Tables `tradingview_prices_1h` and `tv_fetch_progress`
- [x] Fetch script `scripts/fetch_tradingview_1h.py` (resume, retries, heartbeat, `--status` / `--watch`), tested on fake data only
- [x] File loader `scripts/load_tradingview_1h.py`
- [ ] **Blocked:** installing `tvdatafeed` (unofficial, from GitHub) was denied by the sandbox. Table has 0 bars.
- Next steps:
  1. `uv pip install --python .venv/bin/python websocket-client "git+https://github.com/rongardF/tvdatafeed.git"`
  2. `.venv/bin/python scripts/fetch_tradingview_1h.py --limit 5`
  3. Full run
- Open risks: may breach TradingView terms; real fetch call untested; 5,000 bars per request may need paging; ticker mapping for `&` and `-` is a guess; history depth depends on plan. Set `TV_USERNAME` / `TV_PASSWORD` in the shell only.

## Cannot be done from this session
- TradingView chart layouts (3 charts: 1M / 1W / 1D with RSI), adding indicators to charts, reading the open symbol: the MCP has no chart tools, and neither browser nor computer-use tools were available. Do these in the TradingView app.

## Open items
- [ ] RSI showing 75/25 on TradingView: need to know whether it is the built-in RSI or our script
- [ ] Fix slippage in the RSI/EMA/Bollinger Pine generator (fixed ticks distort old, low prices)
- [ ] Decide on loading BAGMANE from BSE
- [ ] Optional: single-pane monthly/weekly/daily RSI indicator
- [ ] Commit the work (run the secret scan first)

## Other uncommitted work (present before this log started)
Corporate actions (detect/import scripts, parsers, tests, reference CSVs), Python GFS backtest and its tests, `docs/`, and edits to `config/strategies.yaml`, `scripts/niftyta.py`, `data/timeframes.py`, `nl/parse.py`. Status not reviewed here.
