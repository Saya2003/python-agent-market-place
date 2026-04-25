"""CSV and PDF export helpers for transaction audit packs."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Iterable


def transactions_to_csv_bytes(records: Iterable[dict[str, Any]]) -> bytes:
    """Serialize transaction dicts to UTF-8 CSV."""
    rows = list(records)
    buffer = io.StringIO()
    fieldnames = [
        "tx_id",
        "timestamp",
        "sender_wallet",
        "recipient_wallet",
        "amount_usdc",
        "task_description",
        "arc_tx_hash",
        "status",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buffer.getvalue().encode("utf-8")


def transactions_to_pdf_bytes(records: list[dict[str, Any]], title: str = "Transaction audit") -> bytes:
    """Build a compact PDF listing using fpdf2."""
    try:
        from fpdf import FPDF
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install fpdf2 for PDF export: pip install fpdf2") from exc

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, title, ln=True)
    pdf.set_font("Helvetica", size=8)
    pdf.cell(0, 6, f"Generated {datetime.now(timezone.utc).isoformat()} UTC", ln=True)
    pdf.ln(2)
    pdf.set_font("Courier", size=7)

    for row in records[:120]:
        line = (
            f"{str(row.get('timestamp', ''))[:22]} | "
            f"{row.get('sender_wallet', '')} -> {row.get('recipient_wallet', '')} | "
            f"{row.get('amount_usdc', '')} USDC | "
            f"{str(row.get('task_description', ''))[:100]}"
        )
        pdf.multi_cell(0, 4, line)
        pdf.ln(1)

    return pdf.output()
