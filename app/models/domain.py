"""Domain models used by orchestrator, payment, and API layers."""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4


def utc_now_iso() -> str:
    """Return UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class PaymentInstruction:
    """Represents an agent-initiated payment instruction."""

    sender_wallet: str
    recipient_wallet: str
    amount_usdc: float
    task_description: str


@dataclass(slots=True)
class TransactionRecord:
    """Normalized transaction record used for logs and dashboard events."""

    tx_id: str
    timestamp: str
    sender_wallet: str
    recipient_wallet: str
    amount_usdc: float
    task_description: str
    arc_tx_hash: str
    status: str = "confirmed"

    @classmethod
    def from_instruction(cls, instruction: PaymentInstruction, arc_tx_hash: str) -> "TransactionRecord":
        """Build a transaction record from a payment instruction."""
        return cls(
            tx_id=str(uuid4()),
            timestamp=utc_now_iso(),
            sender_wallet=instruction.sender_wallet,
            recipient_wallet=instruction.recipient_wallet,
            amount_usdc=instruction.amount_usdc,
            task_description=instruction.task_description,
            arc_tx_hash=arc_tx_hash,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize record for JSON payloads."""
        return asdict(self)
