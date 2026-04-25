"""Gemini planning client scaffold with function-calling style output."""

from app.models.domain import PaymentInstruction


class GeminiCoordinator:
    """Builds payment-aware task plans (stub for Gemini function calling)."""

    def __init__(self, coordinator_wallet: str, research_wallet: str, writer_wallet: str) -> None:
        self.coordinator_wallet = coordinator_wallet
        self.research_wallet = research_wallet
        self.writer_wallet = writer_wallet

    def plan_task(self, user_prompt: str) -> list[PaymentInstruction]:
        """
        Return payment instructions for a given prompt.

        Replace this method with a real Gemini API call using tool/function calling:
        - send_nanopayment(recipient_wallet, amount_usdc, task_description)
        - check_wallet_balance(wallet_id)
        """
        research_amount = 0.001
        writer_amount = 0.002

        return [
            PaymentInstruction(
                sender_wallet=self.coordinator_wallet,
                recipient_wallet=self.research_wallet,
                amount_usdc=research_amount,
                task_description=f"Research subtask for: {user_prompt}",
            ),
            PaymentInstruction(
                sender_wallet=self.coordinator_wallet,
                recipient_wallet=self.writer_wallet,
                amount_usdc=writer_amount,
                task_description=f"Writing subtask for: {user_prompt}",
            ),
        ]
