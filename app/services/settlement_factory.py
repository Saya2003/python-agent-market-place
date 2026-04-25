"""Construct stub or hybrid Circle+stub settlement client from settings."""

from __future__ import annotations

import re

from app.core.config import Settings
from app.services.circle_transfer import CircleArcTransferClient
from app.services.payment_client import HybridSettlementClient, StubPaymentClient

_RAW_HEX = re.compile(r"^[0-9a-fA-F]{64}$")


def _resolved_entity_raw_hex(settings: Settings) -> str:
    """Raw 64-char hex required for per-request ciphertext generation."""
    raw = (settings.circle_entity_secret_raw_hex or "").strip()
    if raw:
        return raw
    fallback = (settings.circle_entity_secret or "").strip()
    if _RAW_HEX.fullmatch(fallback):
        return fallback
    return ""


def build_settlement_client(settings: Settings) -> HybridSettlementClient:
    """Seed demo balances and attach optional Circle live transfer client."""
    stub = StubPaymentClient()
    stub.seed_balance(settings.coordinator_wallet_id, amount_usdc=100.0)
    stub.seed_balance(settings.research_wallet_id, amount_usdc=0.0)
    stub.seed_balance(settings.writer_wallet_id, amount_usdc=0.0)

    mapping = {}
    if settings.circle_research_wallet_address.strip():
        mapping[settings.research_wallet_id] = settings.circle_research_wallet_address.strip()
    if settings.circle_writer_wallet_address.strip():
        mapping[settings.writer_wallet_id] = settings.circle_writer_wallet_address.strip()

    circle: CircleArcTransferClient | None = None
    if settings.settlement_mode == "circle":
        circle = CircleArcTransferClient(
            api_key=settings.circle_api_key,
            api_base=settings.circle_api_base,
            entity_secret_raw_hex=_resolved_entity_raw_hex(settings),
            coordinator_wallet_uuid=settings.circle_coordinator_wallet_uuid,
            recipient_address_by_wallet_id=mapping,
            blockchain=settings.circle_blockchain,
            usdc_token_id=settings.circle_usdc_token_id or None,
            usdc_token_address=settings.circle_usdc_token_address or None,
        )

    use_circle = settings.settlement_mode == "circle" and circle is not None and circle.ready()
    return HybridSettlementClient(stub, circle, use_circle=use_circle)
