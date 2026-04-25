"""Supabase persistence helpers for transaction records."""

from __future__ import annotations

from typing import Any

try:
    from supabase import create_client
except ImportError:  # pragma: no cover - optional dependency
    create_client = None  # type: ignore[misc, assignment]


class SupabaseTransactionStore:
    """Stores and reads transaction records from a Supabase table."""

    def __init__(
        self,
        url: str,
        key: str,
        table_name: str = "agent_transactions",
        agents_table: str = "marketplace_agents",
    ) -> None:
        self.table_name = table_name
        self.agents_table = agents_table
        self._client: Any = None

        cleaned_url = (url or "").strip()
        cleaned_key = (key or "").strip()
        if not cleaned_url or not cleaned_key:
            return
        if create_client is None:
            return
        self._client = create_client(cleaned_url, cleaned_key)

    @property
    def enabled(self) -> bool:
        """Whether Supabase integration is configured and the package is installed."""
        return self._client is not None

    @property
    def package_installed(self) -> bool:
        """Whether the supabase Python package is available."""
        return create_client is not None

    def insert_transaction(self, record: dict[str, Any]) -> None:
        """Insert one transaction record; no-op when disabled."""
        if not self._client:
            return
        self._client.table(self.table_name).insert(record).execute()

    def list_recent_transactions(self, limit: int = 25) -> list[dict[str, Any]]:
        """Fetch latest transactions in descending timestamp order."""
        if not self._client:
            return []
        response = (
            self._client.table(self.table_name)
            .select("*")
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        return list(response.data or [])

    def count_transactions(self) -> int:
        """Return total number of persisted transactions."""
        if not self._client:
            return 0
        response = self._client.table(self.table_name).select("tx_id", count="exact").execute()
        return int(response.count or 0)

    def list_agents(self) -> list[dict[str, Any]]:
        """Return marketplace agent rows for coordinator hiring logic."""
        if not self._client:
            return []
        try:
            response = (
                self._client.table(self.agents_table)
                .select("*")
                .order("display_name")
                .execute()
            )
            return list(response.data or [])
        except Exception:
            return []
