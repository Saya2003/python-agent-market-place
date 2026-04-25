"""Market context snippet for negotiation (Gemini + optional search tool)."""

from __future__ import annotations


def fetch_market_context(*, api_key: str, model: str, query: str, enable_search: bool) -> str | None:
    """
    Return a short plain-text snippet for pricing or planning context.

    If enable_search is True, tries Gemini with Google Search grounding when the
    installed SDK supports it; otherwise falls back to a plain model answer.
    """
    try:
        import google.generativeai as genai
    except ImportError:
        return None

    genai.configure(api_key=api_key)
    prompt = (
        "In 3-5 bullet points, summarize information relevant to this query. "
        "Mention stablecoins, small payments, and infrastructure costs where useful.\n"
        f"Query: {query}"
    )

    def _generate(extra: dict | None) -> str | None:
        m = genai.GenerativeModel(model, **extra) if extra else genai.GenerativeModel(model)
        response = m.generate_content(prompt)
        text = (response.text or "").strip()
        return text or None

    if enable_search:
        for extra in (
            {"tools": [{"google_search": {}}]},
            None,
        ):
            try:
                out = _generate(extra)
                if out:
                    return out
            except Exception:
                continue
        return None

    try:
        return _generate(None)
    except Exception:
        return None
