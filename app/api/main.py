"""FastAPI app: dashboard, Gemini coordination, exports, Supabase, optional Circle settlement."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.economics import compute_economics
from app.core.events import event_bus
from app.services.export_reports import transactions_to_csv_bytes, transactions_to_pdf_bytes
from app.services.gemini_client import GeminiCoordinator
from app.services.invoice_parser import parse_invoice_image
from app.services.orchestrator import AgentOrchestrator, RunOptions
from app.services.policy_engine import build_policy_engine
from app.services.settlement_factory import build_settlement_client
from app.services.supabase_store import SupabaseTransactionStore
from app.services.tx_logger import TransactionLogger

DASHBOARD_HTML_PATH = Path(__file__).resolve().parents[1] / "ui" / "dashboard.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Capture event loop for thread-safe WebSocket broadcasts from Gemini tools."""
    event_bus.set_main_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="Gemini Agent Marketplace", version="0.2.0", lifespan=lifespan)

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
orchestrator = AgentOrchestrator(
    coordinator=coordinator,
    payment_client=payment_client,
    tx_logger=tx_logger,
    supabase_store=supabase_store,
    policy_engine=policy_engine,
    settings=settings,
)


class RunCycleRequest(BaseModel):
    """Payload for running coordinator cycles."""

    prompt: str = Field(..., min_length=3)
    rounds: int = Field(default=1, ge=1, le=500)
    human_approved: bool = Field(
        default=False,
        description="Set true to allow payments at or above policy_approval_threshold_usdc.",
    )
    use_negotiation: bool = Field(default=True)
    use_grounding: bool = Field(
        default=False,
        description="If true, fetches optional market context before negotiation.",
    )
    force_stub_planning: bool = Field(
        default=False,
        description="If true, skips Gemini even when GEMINI_API_KEY is set.",
    )


class DemoBalanceRequest(BaseModel):
    """Set in-memory coordinator balance for insufficient-funds demos."""

    balance_usdc: float = Field(..., ge=0.0, le=1_000_000.0)


def _all_transactions() -> list[dict[str, Any]]:
    if supabase_store.enabled:
        try:
            return supabase_store.list_recent_transactions(limit=50_000)
        except Exception:
            # Fallback to local logs during transient Supabase/network issues.
            return tx_logger.load_all()
    return tx_logger.load_all()


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    """Serve the built-in demo dashboard UI."""
    if DASHBOARD_HTML_PATH.exists():
        return HTMLResponse(DASHBOARD_HTML_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Dashboard file not found.</h1>", status_code=404)


@app.get("/health")
def health() -> dict:
    """Service health check endpoint."""
    env_ready = bool((settings.supabase_url or "").strip() and (settings.supabase_key or "").strip())
    circle = getattr(payment_client, "_circle", None)
    circle_ready = bool(circle and getattr(circle, "ready", lambda: False)())
    return {
        "status": "ok",
        "environment": settings.app_env,
        "supabase_enabled": supabase_store.enabled,
        "supabase_env_configured": env_ready,
        "supabase_package_installed": supabase_store.package_installed,
        "supabase_table": settings.supabase_table,
        "settlement_mode": settings.settlement_mode,
        "circle_live_ready": circle_ready,
        "gemini_configured": bool((settings.gemini_api_key or "").strip()),
    }


@app.post("/run-cycle")
async def run_cycle(payload: RunCycleRequest) -> dict:
    """Run one or more workflow cycles and settle transactions."""
    options = RunOptions(
        human_approved=payload.human_approved,
        use_negotiation=payload.use_negotiation,
        use_grounding=payload.use_grounding,
        force_stub_planning=payload.force_stub_planning,
    )
    results = []
    for iteration in range(payload.rounds):
        prompt = f"{payload.prompt} [round={iteration + 1}]"
        result = await orchestrator.run_once(prompt, options)
        results.append(result)
    return {"rounds_executed": payload.rounds, "results": results}


@app.post("/demo/coordinator-balance")
def demo_coordinator_balance(payload: DemoBalanceRequest) -> dict:
    """Set coordinator demo balance (failure injection or reset)."""
    payment_client.set_wallet_balance(settings.coordinator_wallet_id, payload.balance_usdc)
    return {
        "wallet_id": settings.coordinator_wallet_id,
        "balance_usdc": payment_client.check_wallet_balance(settings.coordinator_wallet_id),
    }


@app.get("/balances")
def balances() -> dict:
    """Return current balances for demo wallets."""
    return {
        "coordinator": payment_client.check_wallet_balance(settings.coordinator_wallet_id),
        "research": payment_client.check_wallet_balance(settings.research_wallet_id),
        "writer": payment_client.check_wallet_balance(settings.writer_wallet_id),
    }


@app.get("/metrics")
def metrics() -> dict:
    """Return economics summary based on logged transactions."""
    records = _all_transactions()
    economics = compute_economics(
        records=records,
        eth_mainnet_estimated_tx_cost=settings.eth_mainnet_estimated_tx_cost,
    )
    hero = (
        f"{economics['transaction_count']} txs | "
        f"{economics['total_usdc_settled']} USDC settled | "
        f"~${economics['estimated_eth_mainnet_cost']} equiv. mainnet gas avoided vs ${economics['total_usdc_settled']} USDC"
    )
    return {
        **economics,
        "hero_summary": hero,
        "target_reached_50_transactions": economics["transaction_count"] >= 50,
        "arc_explorer_tx_url_template": settings.arc_explorer_tx_url_template or None,
    }


@app.get("/recent-transactions")
def recent_transactions(limit: int = 25) -> dict:
    """Return latest transaction records for initial dashboard rendering."""
    bounded_limit = max(1, min(limit, 200))
    if supabase_store.enabled:
        try:
            items = supabase_store.list_recent_transactions(limit=bounded_limit)
            count = supabase_store.count_transactions()
            return {"items": items, "count": count}
        except Exception:
            records = tx_logger.load_all()
            return {"items": records[-bounded_limit:][::-1], "count": len(records)}

    records = tx_logger.load_all()
    return {"items": records[-bounded_limit:][::-1], "count": len(records)}


@app.get("/agents")
def list_agents() -> dict:
    """Return marketplace agents from Supabase when configured."""
    rows = supabase_store.list_agents() if supabase_store.enabled else []
    return {"items": rows, "source": "supabase" if rows else "none"}


@app.post("/invoice/analyze")
async def analyze_invoice(file: UploadFile = File(...)) -> dict:
    """Multimodal: extract amount/vendor from an invoice or receipt image."""
    if not (settings.gemini_api_key or "").strip():
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not set.")
    raw = await file.read()
    if len(raw) > 8_000_000:
        raise HTTPException(status_code=400, detail="File too large.")
    mime = file.content_type or "image/png"
    try:
        parsed = parse_invoice_image(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            image_bytes=raw,
            mime_type=mime,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return parsed


@app.get("/export/transactions.csv")
def export_transactions_csv() -> Response:
    """Download all known transactions as CSV."""
    data = transactions_to_csv_bytes(_all_transactions())
    return Response(
        content=data,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="agent_transactions.csv"'},
    )


@app.get("/export/transactions.pdf")
def export_transactions_pdf() -> Response:
    """Download a simple PDF audit listing."""
    try:
        pdf_bytes = transactions_to_pdf_bytes(_all_transactions())
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="agent_transactions.pdf"'},
    )


@app.get("/export/audit.json")
def export_audit_json() -> dict:
    """Return full transaction list as JSON for auditors."""
    return {"transactions": _all_transactions()}


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    """Stream transaction and cycle events to dashboard clients."""
    await websocket.accept()
    queue = event_bus.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        event_bus.unsubscribe(queue)
    except Exception:
        event_bus.unsubscribe(queue)
        await asyncio.sleep(0)
