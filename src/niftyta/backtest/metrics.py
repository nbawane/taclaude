from __future__ import annotations

import numpy as np
import pandas as pd

PERIODS_PER_YEAR = {"1D": 252, "1W": 52, "1M": 12}


def performance(equity: pd.Series, trades: pd.DataFrame, exposure: float, periods_per_year: int = 252) -> dict:
    start, end = float(equity.iloc[0]), float(equity.iloc[-1])
    years = len(equity) / periods_per_year
    rets = equity.pct_change().dropna()
    dd = equity / equity.cummax() - 1
    pnl = trades["pnl"] if len(trades) else pd.Series(dtype=float)
    gains, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    return {
        "total_return": end / start - 1,
        "cagr": (end / start) ** (1 / years) - 1 if years > 0 and end > 0 else float("nan"),
        "max_drawdown": float(dd.min()),
        "sharpe": float(rets.mean() / rets.std() * np.sqrt(periods_per_year)) if rets.std() > 0 else float("nan"),
        "trades": int(len(trades)),
        "win_rate": float((pnl > 0).mean()) if len(pnl) else float("nan"),
        "avg_pnl_per_trade": float(pnl.mean()) if len(pnl) else float("nan"),
        "profit_factor": float(gains / losses) if losses > 0 else float("nan"),
        "exposure": exposure,
    }
