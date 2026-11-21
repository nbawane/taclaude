from __future__ import annotations

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_costs(path: Path | str = PROJECT_ROOT / "config" / "costs.yaml") -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def buy_cost_rate(c: dict) -> float:
    """Fraction of buy value charged as costs (excluding slippage, which is applied to price)."""
    gst = c["gst_rate"] * (c["exchange_txn_charge"] + c["sebi_fee"])
    return c["exchange_txn_charge"] + c["sebi_fee"] + gst + c["stamp_duty_buy"]


def sell_cost_rate(c: dict) -> float:
    gst = c["gst_rate"] * (c["exchange_txn_charge"] + c["sebi_fee"])
    return c["exchange_txn_charge"] + c["sebi_fee"] + gst + c["stt_delivery"]
