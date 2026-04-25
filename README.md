# Gemini Agent Marketplace on Arc (Python Scaffold)

Hackathon-ready Python backend and demo UI for an **AI agent marketplace** where specialized agents collaborate on a user task and **pay each other in sub-cent USDC**, with settlement designed for **Circle on Arc** and optional persistence in **Supabase**.

## About Python Agent Marketplace

**Python Agent Marketplace** is a reference implementation of an **agent-to-agent commerce** pattern: instead of one monolithic model doing everything, a **coordinator** agent breaks work into steps and **hires** other agents for concrete subtasks. Each hire is backed by a **real payment intent**—tiny amounts of USDC that stand in for “this agent delivered value” and that you can later wire to **Circle programmable wallets** and **Arc** settlement (including nanopayment-style flows appropriate for per-query or per-output pricing).

### The problem it illustrates

Traditional on-chain payments are a poor fit for **high-frequency, low-value** AI workloads. If every tool call or sub-agent step required a full mainnet ERC-20 transfer, gas alone would dominate the unit economics and autonomous agents could not afford to coordinate at scale. This project is structured so you can argue—and eventually measure—that **Arc + USDC + small transfers** (and Circle’s wallet tooling) make **micropayment-native agent loops** economically plausible, while **Gemini** (via Google AI Studio) provides the reasoning layer that decides **when** to pay, **how much**, and **to whom**.

### How the system is supposed to work

1. **User input** — A natural-language task (for example, “research and draft a brief”) enters the system through the HTTP API or the built-in dashboard.
2. **Planning / coordination** — A coordinator agent (today implemented as a **stub** in `gemini_client.py`, ready to swap for real **Gemini function calling**) decides which subtasks exist and which downstream agents should execute them.
3. **Settlement** — For each subtask, the coordinator triggers a **nanopayment-sized** USDC transfer to the worker agent’s wallet. In the scaffold, `payment_client.py` simulates balances and tx hashes; you replace it with **Circle Wallets SDK** calls so each row in the live feed maps to a real Arc-appropriate transaction.
4. **Observation** — The UI and JSON/Supabase logs show a **live payment feed**, wallet balances, and aggregate **economics** (transaction count, total USDC moved, rough comparison to hypothetical mainnet gas costs) so judges and investors can see both **agent behavior** and **money movement** in one place.

### Agent roles in the demo loop

The scaffold ships with three logical wallets / personas so the story is easy to follow in a pitch:

| Role | Responsibility (story) | Payment pattern (demo) |
|------|-------------------------|-------------------------|
| **Coordinator** | Accepts the user task, plans work, pays specialists | Debits USDC when hiring |
| **Research** | Performs “research” subtasks | Receives small USDC per research step |
| **Writer** | Performs “writing” subtasks | Receives small USDC per writing step |

The exact amounts are small and configurable; the point is to show **many cheap hops** rather than one expensive lump payment.

### Two layers: intelligence vs settlement

- **Intelligence layer (Gemini)** — Reasoning, decomposition of the task, and (when integrated) **tool use** such as `send_nanopayment` and `check_wallet_balance`. This is what makes the demo **Google-prize aligned**: the model is not hard-coded to pay on a fixed schedule; it is structured to **choose** payments as tools.
- **Settlement layer (Circle / Arc)** — Execution of USDC movement and recording of on-chain or platform-level transaction identifiers. The README and code keep this boundary explicit so you can demo **stub → real** without rewriting the orchestrator.

### Data and audit trail

Every simulated (or real) payment produces a **normalized transaction record**: sender, recipient, amount, task description, timestamp, and a transaction hash field intended for **Arc** linkage. Records are:

- **Appended to JSONL** for a simple file-based audit trail, and/or
- **Inserted into Supabase** (`agent_transactions`) when `SUPABASE_URL` and `SUPABASE_KEY` are set, so you can query history, build analytics, or attach a second frontend later.

### Built-in dashboard

The repository includes a **single-page dashboard** served at `/` (not only OpenAPI docs). It shows health-adjacent metrics, wallet balances, a **WebSocket-driven live payment feed**, controls to run multiple rounds, and progress toward a **50+ transaction** demo threshold often required in hackathon judging.

### What “done” looks like for a competitive submission

- **Gemini** — Real API calls with **function calling** for payment tools, ideally with one differentiator (multimodal receipt, grounding, or a stronger planner model for negotiation).
- **Circle / Arc** — Real wallet IDs and **programmatic** USDC flows replacing the in-memory `PaymentClient` stub.
- **Economics** — A scripted or UI-driven run of **50+** recorded transactions plus a short narrative comparing **total USDC** vs **estimated mainnet gas** for the same number of transfers.
- **Supabase** — Table(s) for transactions (and optionally runs, agents, or balance snapshots) so persistence is demonstrably real.

This repository is the **spine** for that story: FastAPI service, orchestration loop, logging, optional database, and judge-friendly UI—all in Python so you can iterate quickly during the hackathon.

## What this scaffold includes

- Multi-agent orchestration loop (`Coordinator -> Research -> Writer`)
- Gemini function-calling tool contract (stub + ready for live integration)
- Payment and balance tools abstraction for Circle/Arc integration
- Transaction logging to JSONL and optional Supabase persistence
- Automated run script for `50+` transactions
- FastAPI + WebSocket stream for a live dashboard event feed

## Quick start

1. Create and activate a virtual environment:

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure environment:

```bash
copy .env.example .env
```

Then edit `.env` with your keys, wallets, and Supabase values.

4. Run the API server:

```bash
python -m uvicorn app.api.main:app --reload
```

5. In a second terminal, run a 50-transaction simulation:

```bash
python scripts/run_simulation.py --rounds 50
```

## Supabase setup

1. Create a Supabase project.
2. In SQL Editor, create the transaction and agent registry tables:

```sql
create table if not exists agent_transactions (
  tx_id text primary key,
  timestamp timestamptz not null,
  sender_wallet text not null,
  recipient_wallet text not null,
  amount_usdc numeric not null,
  task_description text not null,
  arc_tx_hash text not null,
  status text not null
);

create table if not exists marketplace_agents (
  wallet_id text primary key,
  display_name text not null,
  role text not null,
  default_fee_usdc numeric not null default 0.001,
  wallet_address text,
  active boolean not null default true
);

insert into marketplace_agents (wallet_id, display_name, role, default_fee_usdc)
values
  ('wallet_research', 'Research Agent', 'research', 0.001),
  ('wallet_writer', 'Writer Agent', 'writer', 0.002)
on conflict (wallet_id) do nothing;
```

3. Add values to `.env`:

```env
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your_supabase_key
SUPABASE_TABLE=agent_transactions
SUPABASE_AGENTS_TABLE=marketplace_agents
```

If `SUPABASE_URL` and `SUPABASE_KEY` are set, writes and reads use Supabase. Otherwise, the app falls back to local JSON logs.

## Advanced demo features implemented

- **Gemini function calling loop (manual tool execution):**
  - `check_wallet_balance(wallet_id)`
  - `send_nanopayment(recipient_wallet, amount_usdc, task_description)`
  - tool-call traces stream over WebSocket and render in the dashboard.
  - if the Gemini tool path fails at runtime, orchestration automatically falls back to stub planning instead of crashing.
- **Hybrid settlement mode:**
  - `SETTLEMENT_MODE=stub` (default): local deterministic tx hashes.
  - `SETTLEMENT_MODE=circle`: attempts live Circle transfer API calls for Arc-compatible flows when all Circle env values are present.
- **Multimodal invoice parsing endpoint:**
  - `POST /invoice/analyze` parses an uploaded receipt/invoice image with Gemini and returns structured amount/vendor/summary JSON.
- **Negotiation + policy engine:**
  - optional negotiation pass lowers or rejects prices.
  - policy checks enforce max per-payment, daily cap, allowlist, and human approval threshold.
- **Failure-mode demo controls:**
  - `POST /demo/coordinator-balance` lets you lower balance to trigger insufficient-funds behavior in live demos.
- **Grounding toggle:**
  - per-run toggle for market context enrichment before negotiation.
- **Audit exports:**
  - `GET /export/transactions.csv`
  - `GET /export/transactions.pdf`
  - `GET /export/audit.json`
- **Resilience improvements:**
  - `/metrics` and `/recent-transactions` gracefully fall back to local JSON logs when Supabase has transient network errors.
  - dashboard parsing is hardened so non-JSON backend errors do not break the full UI refresh loop.

## API endpoints (current)

- `GET /` dashboard UI
- `GET /health` runtime and integration readiness
- `POST /run-cycle` run orchestrator rounds (supports negotiation/grounding/human approval/stub toggle)
- `POST /demo/coordinator-balance` failure-mode injection (insufficient funds)
- `GET /balances` in-memory logical wallet balances
- `GET /metrics` economics summary
- `GET /recent-transactions` latest transactions feed
- `GET /agents` marketplace agent registry (Supabase-backed)
- `POST /invoice/analyze` multimodal invoice/receipt parsing
- `GET /export/transactions.csv` CSV export
- `GET /export/transactions.pdf` PDF export
- `GET /export/audit.json` full JSON audit payload
- `WS /ws/events` live events (transactions, tool traces, policy blocks, run summaries)

## Environment notes

- `SETTLEMENT_MODE=stub` is safest during development.
- `SETTLEMENT_MODE=circle` requires all Circle live fields:
  - `CIRCLE_API_KEY`
  - `CIRCLE_ENTITY_SECRET_RAW_HEX` (raw 64-char secret used to generate fresh ciphertext per request)
  - `CIRCLE_COORDINATOR_WALLET_UUID`
  - recipient addresses (`CIRCLE_RESEARCH_WALLET_ADDRESS`, `CIRCLE_WRITER_WALLET_ADDRESS`)
  - token identity (`CIRCLE_USDC_TOKEN_ID` or `CIRCLE_USDC_TOKEN_ADDRESS`)
- Current Gemini integration uses `google-generativeai` (deprecated but still functional). The app is structured so you can later migrate to `google.genai` without changing the rest of orchestration.

## Troubleshooting

- **`POST /run-cycle` returns 500**
  - check terminal traceback first (most common causes: quota/rate-limit from Gemini, invalid Circle live config, or policy threshold blocks if not `human_approved=true`).
  - set `force_stub_planning=true` in run payload to keep demo flow running while debugging live Gemini.
- **`GET /metrics` intermittently 500**
  - typically transient Supabase connection resets; app now falls back to local JSON logs.
- **`/invoice/analyze` returns 400**
  - ensure `GEMINI_API_KEY` is set and valid.
  - ensure dependencies are installed: `google-generativeai`, `pillow`, `python-multipart`.
- **Pip fails building `circle`**
  - do not use `circle` from PyPI; use `circle-developer-controlled-wallets` (already in `requirements.txt`).

## Project structure

```text
python-agent-marketplace/
  app/
    api/
      main.py
    core/
      config.py
      events.py
      economics.py
    services/
      gemini_client.py
      gemini_live.py
      circle_transfer.py
      policy_engine.py
      negotiation_service.py
      grounding_service.py
      invoice_parser.py
      export_reports.py
      payment_client.py
      settlement_factory.py
      orchestrator.py
      supabase_store.py
      tx_logger.py
    ui/
      dashboard.html
    models/
      domain.py
  scripts/
    run_simulation.py
  logs/
    .gitkeep
  requirements.txt
  .env.example
```

## Next implementation steps

- Add webhook-based Circle transaction state updates (`SENT`/`CONFIRMED`) and persist those state transitions.
- Add per-agent historical analytics (latency, earned USDC, success rate).
- Add richer explorer linking by setting `ARC_EXPLORER_TX_URL_TEMPLATE` in `.env`.
