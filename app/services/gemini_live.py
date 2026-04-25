"""Live Gemini coordinator with manual function calling for payment tools."""

from __future__ import annotations

from typing import Any, Protocol


class CoordinationCallbacks(Protocol):
    """Hooks invoked when the model requests wallet reads or payments."""

    def on_check_wallet_balance(self, wallet_id: str) -> dict[str, Any]:
        """Return JSON-serializable payload for the model."""

    def on_send_nanopayment(
        self, recipient_wallet: str, amount_usdc: float, task_description: str
    ) -> dict[str, Any]:
        """Return JSON-serializable payload including ok, tx_hash, or error."""


def _build_tool() -> Any:
    from google.generativeai import types as genai_types

    check_balance = genai_types.FunctionDeclaration(
        name="check_wallet_balance",
        description="Read the USDC balance for a logical agent wallet id.",
        parameters={
            "type": "object",
            "properties": {
                "wallet_id": {"type": "string"},
            },
            "required": ["wallet_id"],
        },
    )
    send_payment = genai_types.FunctionDeclaration(
        name="send_nanopayment",
        description="Pay another agent in USDC for completing a subtask. Amount must stay sub-cent for demos.",
        parameters={
            "type": "object",
            "properties": {
                "recipient_wallet": {"type": "string"},
                "amount_usdc": {"type": "number"},
                "task_description": {"type": "string"},
            },
            "required": ["recipient_wallet", "amount_usdc", "task_description"],
        },
    )
    return genai_types.Tool(function_declarations=[check_balance, send_payment])


def run_coordinator_with_tools(
    *,
    api_key: str,
    model: str,
    user_prompt: str,
    coordinator_wallet: str,
    research_wallet: str,
    writer_wallet: str,
    callbacks: CoordinationCallbacks,
) -> dict[str, Any]:
    """
    Run a coordinator turn using Gemini function calling.

    Returns dict with keys: success (bool), tool_trace (list), final_text (str), error (str optional).
    """
    try:
        import google.generativeai as genai
        from google.generativeai import types as genai_types
    except ImportError as exc:  # pragma: no cover
        return {"success": False, "tool_trace": [], "final_text": "", "error": str(exc)}

    genai.configure(api_key=api_key)
    system = (
        "You are the Coordinator agent in an AI services marketplace. "
        f"Your wallet id is {coordinator_wallet!r}. "
        f"You may hire research agent wallet {research_wallet!r} and writer agent wallet {writer_wallet!r}. "
        "Plan the user task, check balances if needed, then pay each specialist small USDC amounts "
        "(for example 0.001 for research and 0.002 for writing) using send_nanopayment. "
        "Keep amounts under 0.01 USDC unless the user explicitly demands more. "
        "After payments succeed, briefly summarize what was done for the user."
    )
    tool = _build_tool()
    model_client = genai.GenerativeModel(
        model_name=model,
        tools=[tool],
        system_instruction=system,
    )
    chat = model_client.start_chat(enable_automatic_function_calling=False)

    tool_trace: list[dict[str, Any]] = []
    response = chat.send_message(user_prompt)
    max_turns = 16

    for _ in range(max_turns):
        if not response.candidates:
            break
        parts = list(response.candidates[0].content.parts)
        function_calls = [p for p in parts if p.function_call and p.function_call.name]
        text_parts = [p.text for p in parts if getattr(p, "text", None)]

        if not function_calls:
            final = "\n".join(t for t in text_parts if t).strip() or (response.text or "")
            return {
                "success": True,
                "tool_trace": tool_trace,
                "final_text": final,
                "error": "",
            }

        reply_parts: list[Any] = []
        for part in function_calls:
            fc = part.function_call
            name = fc.name
            raw_args = fc.args or {}
            args = dict(raw_args) if hasattr(raw_args, "items") else {}
            tool_trace.append({"name": name, "args": args})

            if name == "check_wallet_balance":
                wallet_id = str(args.get("wallet_id", ""))
                out = callbacks.on_check_wallet_balance(wallet_id)
            elif name == "send_nanopayment":
                out = callbacks.on_send_nanopayment(
                    str(args.get("recipient_wallet", "")),
                    float(args.get("amount_usdc", 0) or 0),
                    str(args.get("task_description", "")),
                )
            else:
                out = {"ok": False, "error": f"Unknown tool {name}"}

            tool_trace.append({"name": name, "result": out})
            reply_parts.append(
                genai_types.Part.from_function_response(
                    name=name,
                    response={"result": out},
                )
            )

        response = chat.send_message(reply_parts)

    return {
        "success": False,
        "tool_trace": tool_trace,
        "final_text": "",
        "error": "Exceeded maximum coordinator turns without finishing.",
    }
