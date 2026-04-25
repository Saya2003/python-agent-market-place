"""Circle/Arc payment client: in-memory stub and optional live Circle transfer."""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING, Optional

from app.models.domain import PaymentInstruction

if TYPE_CHECKING:
    from app.services.circle_transfer import CircleArcTransferClient


class StubPaymentClient:
    """In-memory USDC balances and deterministic demo transaction hashes."""

    def __init__(self) -> None:
        self._balances: dict[str, float] = {}

    def seed_balance(self, wallet_id: str, amount_usdc: float) -> None:
        """Set initial test balance for a wallet."""
        self._balances[wallet_id] = float(amount_usdc)

    def check_wallet_balance(self, wallet_id: str) -> float:
        """Return current wallet balance."""
        return float(self._balances.get(wallet_id, 0.0))

    def set_wallet_balance(self, wallet_id: str, amount_usdc: float) -> None:
        """Set balance for demo / failure injection."""
        self._balances[wallet_id] = float(amount_usdc)

    def _synthetic_hash(self, instruction: PaymentInstruction) -> str:
        hash_input = (
            f"{instruction.sender_wallet}:{instruction.recipient_wallet}:"
            f"{instruction.amount_usdc}:{instruction.task_description}"
        )
        return "0x" + sha256(hash_input.encode("utf-8")).hexdigest()[:64]

    def apply_transfer_balances(self, instruction: PaymentInstruction) -> None:
        """Move balances without external settlement (used after live Circle call)."""
        sender_balance = self.check_wallet_balance(instruction.sender_wallet)
        if sender_balance < instruction.amount_usdc:
            raise ValueError(
                f"Insufficient funds in {instruction.sender_wallet}. "
                f"Required={instruction.amount_usdc:.6f}, Available={sender_balance:.6f}"
            )
        self._balances[instruction.sender_wallet] = sender_balance - instruction.amount_usdc
        self._balances[instruction.recipient_wallet] = (
            self.check_wallet_balance(instruction.recipient_wallet) + instruction.amount_usdc
        )

    def send_nanopayment(self, instruction: PaymentInstruction) -> str:
        """Execute a simulated nanopayment and return a demo Arc-style hash."""
        self.apply_transfer_balances(instruction)
        return self._synthetic_hash(instruction)


class HybridSettlementClient:
    """
    Uses Circle REST transfer when configured and ready; otherwise stub settlement.

    In-memory balances stay in sync for dashboard demos even when Circle is live.
    """

    def __init__(
        self,
        stub: StubPaymentClient,
        circle: Optional["CircleArcTransferClient"],
        *,
        use_circle: bool,
    ) -> None:
        self._stub = stub
        self._circle = circle
        self._use_circle = use_circle

    def seed_balance(self, wallet_id: str, amount_usdc: float) -> None:
        self._stub.seed_balance(wallet_id, amount_usdc)

    def check_wallet_balance(self, wallet_id: str) -> float:
        return self._stub.check_wallet_balance(wallet_id)

    def set_wallet_balance(self, wallet_id: str, amount_usdc: float) -> None:
        """Override balance for demo scenarios (coordinator drain, reset, etc.)."""
        self._stub.set_wallet_balance(wallet_id, amount_usdc)

    def send_nanopayment(self, instruction: PaymentInstruction) -> str:
        if self._use_circle and self._circle is not None and self._circle.ready():
            circle_id = self._circle.create_transfer(instruction)
            self._stub.apply_transfer_balances(instruction)
            return f"0xCircleTx:{circle_id}"

        return self._stub.send_nanopayment(instruction)
