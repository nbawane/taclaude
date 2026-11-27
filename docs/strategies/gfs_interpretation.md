# GFS: implementation choices where the spec is open

Companion to `gfs_spec.md`. The spec is the truth. These are the choices the code makes where
the spec leaves room. Change any of them only with the user's approval, and update this file.

## Timeframes and lookahead
- Grandfather and Father RSI for a Son bar dated d use the last closed higher-timeframe bar whose
  period end is strictly before d. Forming bars are never used.
- Son bars are closed daily bars. The current, still-forming bar is never used for a decision.

## Pullback and divergence
- "Within the last 5 bars" includes the current bar.
- Swing low: a bar whose low is the strict minimum of the two bars on each side. It is confirmed
  two bars later, and only used from that bar onward.
- Divergence (mode 2): the second swing low must be within the last 5 bars and have Son RSI in
  35 to 45. A prior swing low 10 to 30 bars earlier must have a higher low price and a lower RSI.
  Both the Son RSI and the price low are compared against that prior swing low.
- Mode 2 also requires the Grandfather and Father conditions and the pullback, as in mode 1.

## Entry
- The alert bar is the bar that satisfies the trigger. Buy stop at the alert bar's high. Orders are
  live for the next 2 bars.
- Cancelled if the alert bar's low is breached before the stop fills.
- If the next open is already above the stop, the fill is at the open (gap fill).
- Only one position at a time. New alerts are ignored while a position is open or an alert is live.

## Stop and exits
- Stop loss: the alert bar's low. The spec also allows "swing low"; the code uses the alert low only.
- Mode A: target = entry + 2.5 × (entry − stop).
- Mode B: when Son RSI closes at or above 60, sell 50% at the next open and move the stop to
  break-even. Sell the rest at the next open after Son RSI closes below 55.
  "Trail the rest" is implemented as the break-even stop plus the RSI-55 exit. No price-based
  trailing stop is used, because the spec gives none.
- Mode B trades that never reach RSI 60 are closed only by the stop, or held to the end of the data.
- Same-bar ordering when a bar touches both the stop and the target: the stop is taken first.

## In-sample and out-of-sample slices
- Signals and the exit RSI are computed on the full history, then each period is simulated on its own
  slice. Each period starts flat; a position open at the split is not carried across.

## Costs and sizing
- All-in sizing (100% of cash, whole shares), as for the other strategies.
- Costs and slippage from `config/costs.yaml`, applied on both sides.

## Metrics
- Expectancy is reported in R (profit or loss divided by initial risk), averaged over trades.
- Win rate, profit factor and max drawdown follow `src/niftyta/backtest/metrics.py`.
