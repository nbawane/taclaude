## **Recommended tech stack for your backtesting platform**

| Layer                   | Technology                        | Purpose                                              |
| ----------------------- | --------------------------------- | ---------------------------------------------------- |
| Programming language    | **Python 3.12**                   | Core application and calculations                    |
| Data processing         | **Pandas + NumPy**                | Historical data manipulation                         |
| Technical indicators    | **TA-Lib**                        | RSI, EMA, MACD, Bollinger Bands, ATR, ADX            |
| Primary backtesting     | **VectorBT**                      | Strategy execution and portfolio simulation          |
| Secondary backtesting   | **Backtesting.py**                | Independent strategy validation                      |
| Event-driven execution  | **Custom Python execution layer** | Realistic order fills, SL/TP and position management |
| Historical data         | **Yahoo Finance / Broker API**    | OHLCV market data                                    |
| Data storage            | **Parquet**                       | Efficient historical market data storage             |
| Database                | **SQLite**                        | Strategy configurations and backtest results         |
| Visualization           | **Plotly**                        | Interactive candlestick and performance charts       |
| Dashboard               | **Streamlit**                     | Web-based user interface                             |
| Optimization            | **Optuna**                        | Strategy parameter optimization                      |
| Testing                 | **Pytest**                        | Automated testing and result validation              |
| Reporting               | **Pandas + Excel / CSV**          | Export trades and performance reports                |
| Version control         | **Git + GitHub**                  | Source code management                               |
| Development environment | **VS Code**                       | Python development                                   |

## **My recommended combination**

# **Core stack**

[File:Python logo 01.svg - Wikimedia Commons](https://images.openai.com/static-rsc-4/4WQnbUUJdvO4G_O54H-9RXYeiNC8ap-hadl7zQO_37z43QV44clQv_3mffdRKUsamUYFp5veqRIRVDSmAnDHlkj1JtcAh46t9rVGeEsTz7Kfg4qMWcGYIrrsCkO7nIRnHcOOcRu-Lm-tFOE47ydEtspq6XPPqxxyX0kFOlIlqkM?purpose=inline)

**Python** – Core programming

[TA-Lib辞典｜minaul](https://images.openai.com/static-rsc-4/bjetZJqsS4uOFtMMGRIMO9LEgFX_KNhP90mLkFOrqkpalGygJpXHKEn-JMj5kGrDkU159n1g5w42E-GwrIZeYrHqMuZlUhQUVFP_SHj_HPFGYGBUWPHD-qp8XHL2XiHYM47hfwZsi6KInCNk5SxZLKk-R47uPr_QsUVbal5SDCg?purpose=inline)

**TA-Lib** – Indicator calculations

[What is VectorBT? Essential Guide for Quant Traders](https://images.openai.com/static-rsc-4/U8OZ4d0P51WIyWZoQylN65C7inmVpGHm-CazXvB4qmriZRhmdWy50UVElfjpYHkRIcrNnijJZW9AGGQv2I8KdzFRA90FC_XUT1yoq26nOxkCL-58Rsfi__OOasZxGSWe7D9PjJNWL_uG6HMTYz2WOuPKc0EK83R8aw981WioD-E?purpose=inline)

**VectorBT** – Backtesting engine

[Plotly Announces Dash Enterprise 5.6: Build Data Apps Smarter with Plotly AI](https://images.openai.com/static-rsc-4/rS8kTEPTGPx3gRAAr5YDR2v7C6ADmz7cLl4KafIfSxIs7yXgj_zv4D0gPX6vt74Is5dtMFcwpt7tNSfZGyFzX-4NM9Yj-64m5vdGekdR8aUoNjydVNcWY6M_pqfN6c60OQtTVSZBNbzG2rgQ-oKPcSAJYiTraBjUk9uxaVRloac?purpose=inline)

**Plotly** – Interactive charts

[JHub Apps | JHub Apps](https://images.openai.com/static-rsc-4/GISPLmzeKXJDPu8vrN1ckh8PtB-7yqiEtG8Zb7CLo13RuPNFbdtyP-OgUDAA6MkjxzlDMRAYdc4SE8GVGluOji4LcKiy8-KcOkl-wSKrwo4fhEZQi4wmZBxklhO0WJ_gG6pbLvXVsqyMNmUQA-iC7DRHELRs3E_iNgldYafSeSg?purpose=inline)

**Streamlit** – Dashboard

[Seungjae Ryan Lee](https://images.openai.com/static-rsc-4/5btCrb5T2nAQgpP5UikBmMJkXLK-y7RiP8Y6ALAOLmK36hBYitqXqwiFbFxUP-MeZRJ3DKzcMt_RTwPr-GJK4LZZxbvINbtgQgaBcI4G6cCqPLlqXLDsGAaUageD26GMAlTb5gq8yBpy-yWFzVGP3CGkYhOiZH5xkAroIRfZkh8?purpose=inline)

**Optuna** – Optimization

Recommended architecture

Python + TA-Lib + VectorBT + Plotly + Streamlit

**Important:** Keep the backtesting engine independent of Claude. All calculations and results must be generated and stored by Python.
## Decisions (2026-11-27)

These override the table above where they differ.

| Layer | Decision |
| --- | --- |
| Charts | Always interactive, in the Streamlit app (`.venv/bin/streamlit run app.py`): TradingView Lightweight Charts for price, Plotly for equity, drawdown and stock comparison |
| Storage and database | Keep DuckDB (one local file) instead of Parquet + SQLite |
| Primary backtesting | Keep the project's own engine; VectorBT stays as a cross-check in tests |
| Python | 3.11 for now (project allows 3.11 to 3.12) |
| Later | Backtesting.py for a second opinion; Optuna only with out-of-sample testing |

Still to convert: the HTML report from `scripts/mtf_sma.py` and the PNG reports use Matplotlib.
