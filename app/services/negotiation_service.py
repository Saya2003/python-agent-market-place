"""Optional pricing negotiation pass before executing a payment."""

from __future__ import annotations

import json
import re
from typing import Any


def negotiate_max_amount(
    *,
    api_key: str,
    model: str,
    coordinator_wallet: str,
    recipient_wallet: str,
    proposed_amount_usdc: float,
    task_description: str,
    market_context: str | None,
) -> dict[str, Any]:
    """
    Ask Gemini to approve or lower the proposed micropayment.

    Returns dict with keys: approved (bool), max_amount_usdc (float), rationale (str).
    """
    try:
        import google.generativeai as genai
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install google-generativeai for negotiation.") from exc

    genai.configure(api_key=api_key)
    context_block = f"\nMarket context:\n{market_context}\n" if market_context else ""
    prompt = (
        "You are a strict treasury bot for an AI agent marketplace. "
        "Given a proposed USDC nanopayment, respond ONLY with compact JSON, no markdown.\n"
        f"Coordinator wallet: {coordinator_wallet}\n"
        f"Recipient wallet: {recipient_wallet}\n"
        f"Proposed amount (USDC): {proposed_amount_usdc}\n"
        f"Task: {task_description}\n"
        f"{context_block}"
        'Schema: {"approved": true|false, "max_amount_usdc": number, "rationale": "short string"}\n'
        "Rules: max_amount_usdc must be <= proposed amount and >= 0. "
        "If the task is reasonable for the price, approve true with max_amount_usdc equal to proposed."
    )
    model_client = genai.GenerativeModel(model)
    response = model_client.generate_content(prompt)
    text = (response.text or "").strip()
    json_blob = text
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            json_blob = match.group(1).strip()
    data = json.loads(json_blob)
    approved = bool(data.get("approved", True))
    max_amount = float(data.get("max_amount_usdc", proposed_amount_usdc))
    rationale = str(data.get("rationale", ""))
    max_amount = max(0.0, min(max_amount, proposed_amount_usdc))
    return {"approved": approved, "max_amount_usdc": max_amount, "rationale": rationale}
