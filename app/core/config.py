"""Application configuration loaded from environment variables."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for API, Gemini, Circle, Supabase, and policy."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_model_negotiation: str = "gemini-2.0-flash"
    gemini_enable_grounding: bool = False

    circle_api_key: str = ""
    circle_entity_secret: str = ""
    circle_api_base: str = "https://api.circle.com"
    settlement_mode: str = "stub"
    circle_entity_secret_raw_hex: str = ""
    circle_coordinator_wallet_uuid: str = ""
    circle_research_wallet_address: str = ""
    circle_writer_wallet_address: str = ""
    circle_blockchain: str = "ARC-TESTNET"
    circle_usdc_token_id: str = ""
    circle_usdc_token_address: str = ""

    supabase_url: str = ""
    supabase_key: str = ""
    supabase_table: str = "agent_transactions"
    supabase_agents_table: str = "marketplace_agents"

    coordinator_wallet_id: str = "wallet_coordinator"
    research_wallet_id: str = "wallet_research"
    writer_wallet_id: str = "wallet_writer"

    log_path: str = "logs/transactions.jsonl"
    eth_mainnet_estimated_tx_cost: float = 0.75
    arc_explorer_tx_url_template: str = ""

    policy_max_payment_usdc: float = 0.01
    policy_daily_cap_usdc: float = 50.0
    policy_wallet_allowlist: str = ""
    policy_approval_threshold_usdc: float = 0.002

    @field_validator("settlement_mode")
    @classmethod
    def normalize_settlement_mode(cls, value: str) -> str:
        return (value or "stub").strip().lower()


settings = Settings()
