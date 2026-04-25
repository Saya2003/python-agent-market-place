"""Core loop: Gemini tools (or stub plan), policy, negotiation, settlement, persistence."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.events import event_bus
from app.models.domain import PaymentInstruction, TransactionRecord
from app.services.gemini_client import GeminiCoordinator
from app.services.gemini_live import run_coordinator_with_tools
from app.services.grounding_service import fetch_market_context
from app.services.negotiation_service import negotiate_max_amount
from app.services.payment_client import HybridSettlementClient
from app.services.policy_engine import PolicyEngine
from app.services.supabase_store import SupabaseTransactionStore
from app.services.tx_logger import TransactionLogger


@dataclass
class RunOptions:
    """Per-run toggles for planning, negotiation, and policy."""

    human_approved: bool = False
    use_negotiation: bool = True
    use_grounding: bool = False
    force_stub_planning: bool = False


class AgentOrchestrator:
    """Runs agent-to-agent workflows and records each settlement event."""

    def __init__(
        self,
        coordinator: GeminiCoordinator,
        payment_client: HybridSettlementClient,
        tx_logger: TransactionLogger,
        supabase_store: SupabaseTransactionStore | None,
        policy_engine: PolicyEngine,
        settings: Settings,
    ) -> None:
        self.coordinator = coordinator
        self.payment_client = payment_client
        self.tx_logger = tx_logger
        self.supabase_store = supabase_store
        self.policy_engine = policy_engine
        self.settings = settings

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        event_bus.publish_fire_and_forget({"type": event_type, "payload": payload})

    @staticmethod
    def _compact_error(message: str, limit: int = 420) -> str:
        """Keep UI-visible errors short and readable."""
        clean = " ".join((message or "").split())
        if len(clean) <= limit:
            return clean
        return clean[:limit] + " ..."

    def _log_and_store(self, record: TransactionRecord) -> dict[str, Any]:
        payload = record.to_dict()
        self.tx_logger.append(record)
        if self.supabase_store and self.supabase_store.enabled:
            try:
                self.supabase_store.insert_transaction(payload)
            except Exception as exc:  # pragma: no cover - network
                self._emit("db_error", {"message": str(exc)[:500]})
        return payload

    def _execute_payment(self, instruction: PaymentInstruction) -> dict[str, Any]:
        """Policy, optional negotiation, settlement, logging."""
        policy_result = self.policy_engine.evaluate(
            instruction,
            human_approved=self._current_human_approved,
        )
        if not policy_result.allowed:
            self._emit(
                "policy_block",
                {"reason": policy_result.reason, "instruction": asdict(instruction)},
            )
            return {"ok": False, "error": policy_result.reason}

        working = instruction
        if self._current_use_negotiation and (self.settings.gemini_api_key or "").strip():
            try:
                market = None
                if self._current_use_grounding:
                    market = fetch_market_context(
                        api_key=self.settings.gemini_api_key,
                        model=self.settings.gemini_model,
                        query="USDC micropayments Arc testnet agent marketplace fees",
                        enable_search=bool(self.settings.gemini_enable_grounding),
                    )
                neg = negotiate_max_amount(
                    api_key=self.settings.gemini_api_key,
                    model=self.settings.gemini_model_negotiation,
                    coordinator_wallet=working.sender_wallet,
                    recipient_wallet=working.recipient_wallet,
                    proposed_amount_usdc=working.amount_usdc,
                    task_description=working.task_description,
                    market_context=market,
                )
                self._emit("negotiation", neg)
                if not neg.get("approved", True):
                    return {"ok": False, "error": neg.get("rationale", "Negotiation rejected payment.")}
                max_amt = float(neg.get("max_amount_usdc", working.amount_usdc))
                if max_amt < working.amount_usdc:
                    working = PaymentInstruction(
                        sender_wallet=working.sender_wallet,
                        recipient_wallet=working.recipient_wallet,
                        amount_usdc=max_amt,
                        task_description=working.task_description + " (negotiated down)",
                    )
                policy_retry = self.policy_engine.evaluate(
                    working,
                    human_approved=self._current_human_approved,
                )
                if not policy_retry.allowed:
                    return {"ok": False, "error": policy_retry.reason}
            except Exception as exc:  # pragma: no cover - model JSON
                raw = str(exc)
                compact = self._compact_error(raw)
                self._emit("negotiation_error", {"message": compact})

                lowered = raw.lower()
                quota_hit = ("429" in lowered) or ("quota" in lowered) or ("rate limit" in lowered)
                if quota_hit:
                    self._current_use_negotiation = False
                    self._emit(
                        "negotiation_disabled",
                        {
                            "reason": "Gemini quota/rate-limit reached; negotiation disabled for remaining steps in this run.",
                        },
                    )
                return {"ok": False, "error": f"Negotiation failed: {compact}"}

        try:
            tx_hash = self.payment_client.send_nanopayment(working)
        except ValueError as exc:
            self._emit("payment_error", {"message": str(exc)})
            return {"ok": False, "error": str(exc)}

        self.policy_engine.record_spend(working.sender_wallet, working.amount_usdc)
        record = TransactionRecord.from_instruction(working, tx_hash)
        payload = self._log_and_store(record)
        self._emit("transaction", payload)
        return {"ok": True, "tx_hash": tx_hash, "amount_usdc": working.amount_usdc}

    async def run_once(self, user_prompt: str, options: RunOptions | None = None) -> dict[str, Any]:
        """Run one coordinator cycle (Gemini tools or stub plan) and settle payments."""
        opts = options or RunOptions()
        self._current_human_approved = opts.human_approved
        self._current_use_negotiation = opts.use_negotiation
        self._current_use_grounding = opts.use_grounding

        agents_note = ""
        if self.supabase_store and self.supabase_store.enabled:
            rows = self.supabase_store.list_agents()
            if rows:
                agents_note = "\nRegistered marketplace agents from database:\n" + "\n".join(
                    f"- {r.get('display_name', r.get('wallet_id'))}: wallet_id={r.get('wallet_id')} "
                    f"role={r.get('role')} default_fee_usdc={r.get('default_fee_usdc')}"
                    for r in rows[:12]
                )

        use_live = bool((self.settings.gemini_api_key or "").strip()) and not opts.force_stub_planning

        if use_live:

            class _Cb:
                def on_check_wallet_balance(cb_self, wallet_id: str) -> dict[str, Any]:
                    bal = self.payment_client.check_wallet_balance(wallet_id)
                    out = {"wallet_id": wallet_id, "balance_usdc": bal}
                    self._emit("gemini_tool", {"name": "check_wallet_balance", "args": {"wallet_id": wallet_id}, "result": out})
                    return out

                def on_send_nanopayment(
                    cb_self, recipient_wallet: str, amount_usdc: float, task_description: str
                ) -> dict[str, Any]:
                    self._emit(
                        "gemini_tool",
                        {
                            "name": "send_nanopayment",
                            "args": {
                                "recipient_wallet": recipient_wallet,
                                "amount_usdc": amount_usdc,
                                "task_description": task_description,
                            },
                            "result": None,
                        },
                    )
                    instruction = PaymentInstruction(
                        sender_wallet=self.settings.coordinator_wallet_id,
                        recipient_wallet=recipient_wallet,
                        amount_usdc=float(amount_usdc),
                        task_description=task_description,
                    )
                    return self._execute_payment(instruction)

            prompt = user_prompt + agents_note
            try:
                gemini_out = await asyncio.to_thread(
                    run_coordinator_with_tools,
                    api_key=self.settings.gemini_api_key,
                    model=self.settings.gemini_model,
                    user_prompt=prompt,
                    coordinator_wallet=self.settings.coordinator_wallet_id,
                    research_wallet=self.settings.research_wallet_id,
                    writer_wallet=self.settings.writer_wallet_id,
                    callbacks=_Cb(),
                )
                self._emit("gemini_session", gemini_out)
                if gemini_out.get("success", False):
                    summary: dict[str, Any] = {
                        "prompt": user_prompt,
                        "mode": "gemini_tools",
                        "gemini": gemini_out,
                        "transactions": [],  # individual txs already emitted
                    }
                    await event_bus.publish({"type": "cycle_complete", "payload": summary})
                    return summary
                self._emit("gemini_error", {"message": gemini_out.get("error", "Gemini tool run failed")})
            except Exception as exc:  # pragma: no cover - defensive fallback
                self._emit("gemini_error", {"message": str(exc)[:500]})

        instructions = self.coordinator.plan_task(user_prompt + agents_note)
        records: list[dict] = []
        for instruction in instructions:
            self._emit(
                "stub_plan",
                {
                    "sender": instruction.sender_wallet,
                    "recipient": instruction.recipient_wallet,
                    "amount_usdc": instruction.amount_usdc,
                },
            )
            out = self._execute_payment(instruction)
            if out.get("ok") and "tx_hash" in out:
                records.append(
                    {
                        "tx_hash": out["tx_hash"],
                        "amount_usdc": out.get("amount_usdc"),
                        "task_description": instruction.task_description,
                    }
                )
            else:
                records.append({"error": out.get("error", "unknown")})

        summary = {
            "prompt": user_prompt,
            "mode": "stub_plan",
            "instruction_count": len(instructions),
            "transactions": records,
        }
        await event_bus.publish({"type": "cycle_complete", "payload": summary})
        return summary
