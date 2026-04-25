"""Circle Developer Wallets transfer API (optional live settlement on Arc testnet)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from app.models.domain import PaymentInstruction


class CircleTransferError(RuntimeError):
    """Raised when Circle transfer API returns an error."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _fresh_entity_secret_ciphertext(api_key: str, entity_secret_raw_hex: str) -> str:
    """Encrypt entity secret for a single request (Circle requires unique ciphertext per call)."""
    try:
        from circle.web3 import utils as circle_utils
    except ImportError as exc:  # pragma: no cover
        raise CircleTransferError(
            "Install circle package for live settlement: pip install circle"
        ) from exc
    return circle_utils.generate_entity_secret_ciphertext(api_key, entity_secret_raw_hex)


class CircleArcTransferClient:
    """
    POST /v1/w3s/developer/transactions/transfer for USDC on Arc testnet.

    Requires coordinator wallet UUID and on-chain destination addresses for payees.
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_base: str,
        entity_secret_raw_hex: str,
        coordinator_wallet_uuid: str,
        recipient_address_by_wallet_id: dict[str, str],
        blockchain: str,
        usdc_token_id: str | None,
        usdc_token_address: str | None,
    ) -> None:
        self.api_key = api_key.strip()
        self.api_base = api_base.rstrip("/")
        self.entity_secret_raw_hex = entity_secret_raw_hex.strip()
        self.coordinator_wallet_uuid = coordinator_wallet_uuid.strip()
        self.recipient_address_by_wallet_id = {
            k.strip(): v.strip() for k, v in recipient_address_by_wallet_id.items() if k and v
        }
        self.blockchain = blockchain.strip()
        self.usdc_token_id = (usdc_token_id or "").strip() or None
        self.usdc_token_address = (usdc_token_address or "").strip() or None

    def ready(self) -> bool:
        """True when minimum configuration exists for a transfer attempt."""
        return bool(
            self.api_key
            and self.entity_secret_raw_hex
            and self.coordinator_wallet_uuid
            and self.recipient_address_by_wallet_id
            and (self.usdc_token_id or self.usdc_token_address)
        )

    def create_transfer(self, instruction: PaymentInstruction) -> str:
        """
        Initiate transfer from developer-controlled coordinator wallet.

        Returns Circle transaction id (string). Caller may prefix for logs.
        """
        if not self.ready():
            raise CircleTransferError("Circle transfer client is not fully configured.")

        dest = self.recipient_address_by_wallet_id.get(instruction.recipient_wallet)
        if not dest:
            raise CircleTransferError(
                f"No destination address mapped for wallet id {instruction.recipient_wallet!r}. "
                "Set CIRCLE_RESEARCH_WALLET_ADDRESS and CIRCLE_WRITER_WALLET_ADDRESS (or extend mapping)."
            )

        ciphertext = _fresh_entity_secret_ciphertext(self.api_key, self.entity_secret_raw_hex)
        idempotency_key = str(uuid.uuid4())
        request_id = str(uuid.uuid4())

        payload: dict[str, Any] = {
            "idempotencyKey": idempotency_key,
            "entitySecretCiphertext": ciphertext,
            "walletId": self.coordinator_wallet_uuid,
            "destinationAddress": dest,
            "amounts": [f"{instruction.amount_usdc:.8f}".rstrip("0").rstrip(".")],
            "feeLevel": "MEDIUM",
            "blockchain": self.blockchain,
            "refId": instruction.task_description[:120],
        }
        if self.usdc_token_id:
            payload["tokenId"] = self.usdc_token_id
        else:
            payload["tokenAddress"] = self.usdc_token_address
            payload["tokenBlockchain"] = self.blockchain

        url = f"{self.api_base}/v1/w3s/developer/transactions/transfer"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Request-Id": request_id,
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, content=json.dumps(payload))

        if response.status_code not in (200, 201):
            raise CircleTransferError(
                f"Circle transfer failed: HTTP {response.status_code}",
                status_code=response.status_code,
                body=response.text[:2000],
            )

        data = response.json().get("data") or {}
        tx_id = data.get("id")
        if not tx_id:
            raise CircleTransferError(f"Unexpected Circle response: {response.text[:2000]}")
        return str(tx_id)
