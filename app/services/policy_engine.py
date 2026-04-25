"""Risk and policy checks before executing agent-to-agent payments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Iterable

from app.models.domain import PaymentInstruction

if TYPE_CHECKING:
    from app.core.config import Settings


@dataclass(slots=True)
class PolicyResult:
    """Outcome of evaluating a payment against policy rules."""

    allowed: bool
    reason: str = ""


class PolicyEngine:
    """
    Enforces caps, allowlists, and optional human-in-the-loop thresholds.

    Daily spend is tracked in-process (resets on server restart).
    """

    def __init__(
        self,
        max_payment_usdc: float,
        daily_cap_usdc: float,
        allowlist: Iterable[str] | None,
        approval_threshold_usdc: float,
        known_wallet_ids: set[str],
    ) -> None:
        self.max_payment_usdc = max_payment_usdc
        self.daily_cap_usdc = daily_cap_usdc
        self.allowlist = {w.strip() for w in (allowlist or []) if w.strip()}
        self.approval_threshold_usdc = approval_threshold_usdc
        self.known_wallet_ids = known_wallet_ids
        self._daily_spent: dict[tuple[str, date], float] = {}

    def _today(self) -> date:
        return datetime.now(timezone.utc).date()

    def _spent_today(self, sender: str) -> float:
        return self._daily_spent.get((sender, self._today()), 0.0)

    def record_spend(self, sender: str, amount_usdc: float) -> None:
        """Record successful spend toward daily cap."""
        key = (sender, self._today())
        self._daily_spent[key] = self._daily_spent.get(key, 0.0) + amount_usdc

    def evaluate(
        self,
        instruction: PaymentInstruction,
        *,
        human_approved: bool = False,
    ) -> PolicyResult:
        """Return whether the payment may proceed."""
        if instruction.amount_usdc <= 0:
            return PolicyResult(False, "Amount must be positive.")

        if instruction.amount_usdc > self.max_payment_usdc:
            return PolicyResult(
                False,
                f"Amount {instruction.amount_usdc} exceeds max_payment_usdc={self.max_payment_usdc}.",
            )

        if self.allowlist:
            if instruction.sender_wallet not in self.allowlist:
                return PolicyResult(False, f"Sender {instruction.sender_wallet} is not in allowlist.")
            if instruction.recipient_wallet not in self.allowlist:
                return PolicyResult(False, f"Recipient {instruction.recipient_wallet} is not in allowlist.")

        projected = self._spent_today(instruction.sender_wallet) + instruction.amount_usdc
        if projected > self.daily_cap_usdc:
            return PolicyResult(
                False,
                f"Daily cap exceeded for {instruction.sender_wallet}: "
                f"would be {projected:.6f} > {self.daily_cap_usdc}.",
            )

        if instruction.amount_usdc >= self.approval_threshold_usdc and not human_approved:
            return PolicyResult(
                False,
                f"Amount is at or above approval_threshold_usdc={self.approval_threshold_usdc}; "
                "set human_approved=true on the request to proceed.",
            )

        if instruction.recipient_wallet not in self.known_wallet_ids:
            return PolicyResult(False, f"Unknown recipient wallet id: {instruction.recipient_wallet}.")

        return PolicyResult(True, "")


def build_policy_engine(settings: "Settings") -> PolicyEngine:
    """Build engine from application settings."""
    raw = (settings.policy_wallet_allowlist or "").strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    allowlist = parts or None
    known = {
        settings.coordinator_wallet_id,
        settings.research_wallet_id,
        settings.writer_wallet_id,
    }
    return PolicyEngine(
        max_payment_usdc=settings.policy_max_payment_usdc,
        daily_cap_usdc=settings.policy_daily_cap_usdc,
        allowlist=allowlist,
        approval_threshold_usdc=settings.policy_approval_threshold_usdc,
        known_wallet_ids=known,
    )
