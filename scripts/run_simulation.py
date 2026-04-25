"""Run transaction simulation from CLI and print economics summary."""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.economics import compute_economics
from app.services.gemini_client import GeminiCoordinator
from app.services.orchestrator import AgentOrchestrator, RunOptions
from app.services.policy_engine import build_policy_engine
from app.services.settlement_factory import build_settlement_client
from app.services.supabase_store import SupabaseTransactionStore
from app.services.tx_logger import TransactionLogger


async def run(rounds: int, prompt: str, reset_log: bool) -> None:
    """Execute orchestration rounds and print final metrics."""
    payment_client = build_settlement_client(settings)

    coordinator = GeminiCoordinator(
        coordinator_wallet=settings.coordinator_wallet_id,
        research_wallet=settings.research_wallet_id,
        writer_wallet=settings.writer_wallet_id,
    )
    tx_logger = TransactionLogger(settings.log_path)
    supabase_store = SupabaseTransactionStore(
        url=settings.supabase_url,
        key=settings.supabase_key,
        table_name=settings.supabase_table,
        agents_table=settings.supabase_agents_table,
    )
    policy_engine = build_policy_engine(settings)

    if reset_log:
        tx_logger.replace_all([])

    orchestrator = AgentOrchestrator(
        coordinator=coordinator,
        payment_client=payment_client,
        tx_logger=tx_logger,
        supabase_store=supabase_store,
        policy_engine=policy_engine,
        settings=settings,
    )

    options = RunOptions(
        human_approved=True,
        use_negotiation=False,
        use_grounding=False,
        force_stub_planning=True,
    )

    for index in range(rounds):
        cycle_prompt = f"{prompt} [round={index + 1}]"
        await orchestrator.run_once(cycle_prompt, options)

    records = (
        supabase_store.list_recent_transactions(limit=10000)
        if supabase_store.enabled
        else tx_logger.load_all()
    )
    economics = compute_economics(records, settings.eth_mainnet_estimated_tx_cost)

    print("Simulation complete.")
    print(f"Transactions logged: {economics['transaction_count']}")
    print(f"Total USDC settled: {economics['total_usdc_settled']}")
    print(f"Estimated ETH mainnet cost: {economics['estimated_eth_mainnet_cost']}")
    print(f"Estimated savings vs ETH: {economics['estimated_savings_vs_eth']}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for simulation runs."""
    parser = argparse.ArgumentParser(description="Run agent marketplace simulation")
    parser.add_argument("--rounds", type=int, default=50, help="Number of coordinator cycles to run")
    parser.add_argument("--prompt", type=str, default="Research and draft a market brief", help="Base user task")
    parser.add_argument(
        "--no-reset-log",
        action="store_true",
        help="Append to existing transaction log instead of resetting",
    )
    return parser.parse_args()


if __name__ == "__main__":
    cli_args = parse_args()
    asyncio.run(run(cli_args.rounds, cli_args.prompt, reset_log=not cli_args.no_reset_log))
