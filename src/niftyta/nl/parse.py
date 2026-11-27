"""Rule-based prompt parser (no paid AI API). Understands the readme's example prompts:
stocks or index names, timeframes, strategies, years, and whether to generate Pine Script.
Anything it cannot map is reported back instead of guessed."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..universe import index_symbols

STRATEGY_WORDS = {
    "rsi": "rsi", "ema": "ema_cross", "ema crossover": "ema_cross", "crossover": "ema_cross",
    "bollinger": "bbands", "bollinger band": "bbands", "bollinger bands": "bbands", "bb": "bbands",
    "gfs": "gfs", "grandfather": "gfs", "grandfather father son": "gfs", "divergence": "gfs",
}
UNSUPPORTED = ["macd", "trix", "supertrend", "sma", "stochastic", "adx", "vwap", "ichimoku"]
TIMEFRAME_WORDS = {"daily": "1D", "day": "1D", "weekly": "1W", "week": "1W", "monthly": "1M", "month": "1M"}
INDEX_WORDS = {"nifty50": "NIFTY50", "nifty 50": "NIFTY50", "banknifty": "BANKNIFTY",
               "bank nifty": "BANKNIFTY", "nifty500": "NIFTY500", "nifty 500": "NIFTY500"}
STOP = {"AND", "THE", "FOR", "WITH", "USING", "ON", "IN", "OF", "TO", "BACKTEST", "ANALYZE", "ANALYSE",
        "COMPARE", "TEST", "GENERATE", "PINE", "SCRIPT", "BEST", "STRATEGY", "STRATEGIES", "DAILY",
        "WEEKLY", "MONTHLY", "YEARS", "YEAR", "FIVE", "TEN", "RSI", "EMA", "BOLLINGER", "BANDS", "BAND",
        "MONTH", "WEEK", "DAY", "FIND", "PERFORMING", "AMONG", "THESE", "STOCKS", "STOCK", "COMPARE",
        "TIMEFRAMES", "TIMEFRAME", "ALL", "BUY", "HOLD", "BUYANDHOLD", "PERFORMANCE", "COMPARISON",
        "REPORT", "ON", "CROSSOVER", "CROSS", "FOR", "ALSO", "TRADING", "DATA", "PLEASE", "MACD"}


@dataclass
class Request:
    symbols: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)
    years: int = 10
    pine: bool = False
    unsupported: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def parse_prompt(text: str, known_symbols: set[str]) -> Request:
    low = text.lower()
    req = Request()

    # symbols: index names first, then explicit tickers that exist in the database
    for phrase, idx in INDEX_WORDS.items():
        if phrase in low:
            req.symbols += index_symbols(idx) if idx in ("NIFTY50", "BANKNIFTY") else []
            if idx == "NIFTY500":
                req.notes.append("NIFTY500 list not wired in yet; use explicit stock names.")
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9&\-]*", text):
        up = tok.upper()
        if up in known_symbols and up not in STOP and up not in req.symbols:
            req.symbols.append(up)
    req.symbols = list(dict.fromkeys(req.symbols))

    # timeframes
    for word, tf in TIMEFRAME_WORDS.items():
        if re.search(rf"\b{word}\b", low) and tf not in req.timeframes:
            req.timeframes.append(tf)
    if "all timeframe" in low or "multi" in low or "multiframe" in low or "multi-frame" in low \
            or ("day" in low and "week" in low and "month" in low):
        req.timeframes = ["1D", "1W", "1M"]
    if not req.timeframes:
        req.timeframes = ["1D"]

    # strategies
    for word, key in STRATEGY_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", low) and key not in req.strategies:
            req.strategies.append(key)
    if "gfs" in req.strategies:
        req.strategies = ["gfs"]  # GFS runs on its own; it is not mixed with the other rule sets
    req.strategies = req.strategies or ["rsi", "ema_cross", "bbands"]
    for u in UNSUPPORTED:
        if re.search(rf"\b{u}\b", low):
            req.unsupported.append(u.upper())

    # years
    m = re.search(r"(\d+)\s*(?:years|year|yr)", low)
    if m:
        req.years = int(m.group(1))
    elif "five" in low or "5 y" in low:
        req.years = 5

    req.pine = bool(re.search(r"\bpine\b|tradingview|script", low))
    if not req.symbols:
        req.notes.append("No known stock or index name found in the prompt.")
    return req
