"""Multimodal invoice / receipt parsing with Gemini."""

from __future__ import annotations

import io
import json
import re
from typing import Any


def parse_invoice_image(
    *,
    api_key: str,
    model: str,
    image_bytes: bytes,
    mime_type: str = "image/png",
) -> dict[str, Any]:
    """
    Extract payment-oriented fields from an invoice or receipt image.

    Returns keys: amount_usdc (float|None), vendor (str), summary (str), raw_json (dict).
    """
    try:
        import google.generativeai as genai
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install google-generativeai and pillow for invoice parsing.") from exc

    genai.configure(api_key=api_key)
    model_client = genai.GenerativeModel(model)

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install pillow for image parsing: pip install pillow") from exc

    image = Image.open(io.BytesIO(image_bytes))
    prompt = (
        "You read invoices and receipts. Extract a likely total due in USD/USDC, vendor name, "
        "and a one-line summary. Respond ONLY with minified JSON, no markdown fences.\n"
        'Schema: {"amount_usdc": number|null, "vendor": string, "summary": string}\n'
        "Use null for amount_usdc if unclear."
    )
    response = model_client.generate_content([prompt, image])
    text = (response.text or "").strip()
    json_blob = text
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            json_blob = match.group(1).strip()
    data = json.loads(json_blob)
    amount = data.get("amount_usdc")
    return {
        "amount_usdc": float(amount) if amount is not None else None,
        "vendor": str(data.get("vendor", "")),
        "summary": str(data.get("summary", "")),
        "raw_json": data,
        "mime_type": mime_type,
    }
