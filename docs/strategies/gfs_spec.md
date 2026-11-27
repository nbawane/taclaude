# Bullish GFS (Grandfather-Father-Son) + RSI Divergence: SPECIFICATION

**This file is the source of truth for the GFS strategy.** It is the user's specification,
copied verbatim. If the code, the config or any report disagrees with this file, the code is wrong.
Implementation choices where this text is open are recorded separately in `gfs_interpretation.md`.
Do not edit the rules below without the user's approval.

---

Write a clean, modular Python backtesting script (using backtrader or vectorbt/pandas) for the following "Bullish GFS (Grandfather-Father-Son) + RSI Divergence" trading strategy. Ensure there is zero lookahead bias when resampling higher timeframe RSI values.

STRATEGY RULES:

1. Indicator: 14-period Wilder's RSI on Close.

2. Timeframes: Configurable triplet (default: Grandfather = Monthly, Father = Weekly, Son = Daily). Always use the last *closed* higher-timeframe bar for Grandfather and Father RSI to prevent lookahead bias.

3. Entry Conditions (evaluated on Son timeframe):
   - Grandfather RSI > 60
   - Father RSI > 60
   - Pullback: Son RSI dipped into the 35 to 45 range within the last 5 bars.
   - Trigger Mode 1 (Standard GFS): Son RSI turns up (RSI[0] > RSI[1]) AND current candle is bullish (Close > Open).
   - Trigger Mode 2 (Bullish RSI Divergence): Price makes a lower low compared to a prior swing low (within 10-30 bars) while Son RSI makes a higher low (with the second low in the 35-45 RSI zone), followed by a bullish candle (Close > Open).
   - Execution: Enter Long on a Buy Stop above the Alert Candle's High (valid for 2 bars; cancel if Alert Candle's Low is breached first).

4. Stop Loss & Exits:
   - Stop Loss: Below the Alert Candle's Low (or swing low).
   - Target / Exit: Provide a toggle to test (A) Fixed 1:2.5 Risk-Reward target, or (B) Scale out 50% when Son RSI hits 60, move SL to breakeven, and trail the rest until Son RSI closes below 55.

5. Output: Include metrics for Win Rate, Profit Factor, Max Drawdown, Expectancy, Total Trades, and compare Mode 1 (Standard GFS) vs. Mode 2 (GFS + Divergence).
