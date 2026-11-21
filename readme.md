# Project: Build My Free AI-Powered Technical Analysis and Backtesting System

Act as my quantitative trading developer, Python engineer and technical analysis research assistant.

I want to build a free or zero-cost system where I can give you natural-language prompts and you perform technical analysis, historical backtesting, strategy comparisons and TradingView Pine Script generation.

I do not want to manually write Python code or calculate indicators myself. I want you to coordinate the available tools and automate as much of the workflow as possible.

## 1. My existing resources

- Claude AI
- Zerodha account
- Groww account
- TradingView Free account
- I want to avoid paid APIs, subscriptions and services initially.
- My initial target market is Indian stocks (NSE).
- Start with daily timeframe and five years of historical data.

Do not assume that my accounts provide free API access. Check the actual availability, pricing and permissions before recommending an integration.

## 2. Build the system in phases

### Phase A — Environment and tool setup

First inspect my available Claude environment and capabilities.

Determine whether you can use:
- Local Python execution
- Claude Desktop or Claude Code integrations
- MCP servers
- File creation and reading
- Browser or TradingView interaction, if supported

Recommend the simplest free architecture that works with my environment.

If an integration is unavailable, explain exactly what I need to install or configure. Do not pretend that a tool is connected when it is not.

Use Python with suitable free libraries, such as:
- pandas
- numpy
- yfinance or another suitable free historical data source
- pandas-ta or ta
- vectorbt or backtesting.py, if appropriate
- matplotlib

Keep the design modular so that I can change data providers later.

### Phase B — Historical market data

Build a data retrieval module.

Requirements:
- NSE stock symbols
- Five years of daily OHLCV data
- Date range selection
- Data validation
- Missing candle detection
- Duplicate removal
- Corporate-action and adjusted-price considerations
- Data caching to avoid unnecessary downloads

Start with RELIANCE.

Use a free source where possible. Explain its limitations, especially data quality, availability and licensing.

Never silently fill missing market prices or create fabricated candles.

### Phase C — Technical indicators

Implement these indicators:

1. RSI (14)
2. EMA (9)
3. EMA (21)
4. SMA (20)
5. SMA (50)
6. Bollinger Bands (20, 2 standard deviations)

Allow me to change indicator parameters through natural-language prompts.

### Phase D — Backtesting engine

Build three separate strategies.

**Strategy 1: RSI**

Initial example rules:
- Buy when RSI crosses above 30.
- Sell when RSI crosses below 70.

**Strategy 2: EMA crossover**

Initial example rules:
- Buy when EMA 9 crosses above EMA 21.
- Sell when EMA 9 crosses below EMA 21.

**Strategy 3: Bollinger Bands**

Initial example rules:
- Buy when price closes back above the lower Bollinger Band after closing below it.
- Sell when price closes back below the upper Bollinger Band after closing above it.

Make the entry and exit conditions configurable.

Important:
- Avoid look-ahead bias.
- Calculate signals using completed daily candles.
- Execute simulated trades no earlier than the next available trading session.
- Include brokerage, STT, exchange charges, GST, stamp duty and slippage using configurable assumptions appropriate to the instrument and trading style.
- Do not ignore transaction costs.
- Do not use future information to generate past signals.

### Phase E — Performance comparison

Backtest all three strategies on RELIANCE for five years.

Compare against buy-and-hold.

Generate:
- Total return
- CAGR
- Maximum drawdown
- Win rate
- Number of trades
- Average profit per trade
- Profit factor
- Sharpe ratio
- Exposure to the market
- Equity curve
- Drawdown chart

Separate the data into in-sample and out-of-sample periods. Show whether a strategy performs consistently rather than selecting the best strategy only by total return.

Do not optimize parameters on the test period.

### Phase F — TradingView Pine Script

After identifying the best strategy:

- Generate Pine Script compatible with the currently supported TradingView version.
- Use strategy(), not indicator(), so Strategy Tester can work.
- Include the exact entry and exit rules used by Python.
- Include configurable indicator parameters.
- Include clear buy and sell signals.
- Add plots for relevant indicators.
- Include realistic commission and slippage settings where supported.
- Explain any differences between Python and TradingView execution assumptions.

Provide instructions for pasting the script into TradingView Free and validating the signals.

Do not claim the script has been tested in TradingView unless you actually execute and verify it there.

### Phase G — Natural-language workflow

Once the system works, I want to be able to enter prompts like:

"Analyze RELIANCE on the daily timeframe. Apply RSI 14, EMA 9/21 and Bollinger Bands. Backtest all three strategies for five years. Compare performance. Generate a Pine Script for the best strategy."

Other examples:

"Backtest TCS using RSI 14 and EMA 20/50."

"Compare RSI, MACD and Bollinger Band strategies on INFY."

"Find the best-performing strategy among these 20 NSE stocks."

"Test the EMA crossover strategy on daily, weekly and monthly timeframes."

"Compare the strategy with buy-and-hold."

The system should understand the prompt, retrieve data, run the calculations, produce the report and generate the required Pine Script.

## 3. Report format

For every backtest, generate:

1. Executive summary
2. Data source and date range
3. Strategy rules
4. Performance comparison table
5. Equity curve
6. Drawdown chart
7. Trade history
8. Transaction cost assumptions
9. Out-of-sample results
10. Risks and limitations
11. Pine Script, if requested

Save reports and results in an organized project folder.

## 4. Important constraints

- Keep the initial implementation free.
- Never place live trades.
- Never submit orders through Zerodha or Groww.
- Never ask me to share passwords, OTPs, API secrets or account credentials in chat.
- Do not purchase any subscription or API.
- Ask for my approval before using a paid service.
- Explain every installation step in simple language.
- Do not build everything at once. Complete one phase, test it and then move to the next.

## 5. First task

Do not start coding the entire system immediately.

First:
1. Inspect my available environment.
2. Propose the simplest free architecture.
3. Identify the tools and installations required.
4. Explain which parts can be fully automated and which require manual action.
5. Give me a step-by-step implementation plan.

Wait for my approval before proceeding with the installation and development.