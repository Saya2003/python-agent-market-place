"""Append-only JSONL logger for transaction and economics reporting."""

import json
from pathlib import Path
from typing import Iterable

from app.models.domain import TransactionRecord


class TransactionLogger:
    """Writes transaction records to a JSONL log file."""

    def __init__(self, output_path: str) -> None:
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: TransactionRecord) -> None:
        """Append a single transaction record to disk."""
        with self.output_path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(record.to_dict()) + "\n")

    def load_all(self) -> list[dict]:
        """Load all records from log file."""
        if not self.output_path.exists():
            return []
        lines = self.output_path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def replace_all(self, records: Iterable[TransactionRecord]) -> None:
        """Reset and rewrite log file with the provided records."""
        with self.output_path.open("w", encoding="utf-8") as file_handle:
            for record in records:
                file_handle.write(json.dumps(record.to_dict()) + "\n")
