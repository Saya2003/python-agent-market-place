"""Economics metrics helpers for judge-facing proof points."""

from typing import Iterable


def compute_economics(records: Iterable[dict], eth_mainnet_estimated_tx_cost: float) -> dict:
    """Compute transaction and margin metrics from transaction records."""
    record_list = list(records)
    tx_count = len(record_list)
    total_usdc = sum(float(item["amount_usdc"]) for item in record_list)
    estimated_eth_cost = tx_count * eth_mainnet_estimated_tx_cost
    estimated_savings = estimated_eth_cost - total_usdc

    return {
        "transaction_count": tx_count,
        "total_usdc_settled": round(total_usdc, 6),
        "estimated_eth_mainnet_cost": round(estimated_eth_cost, 6),
        "estimated_savings_vs_eth": round(estimated_savings, 6),
    }
