# ApexOperator

**A production-oriented agentic operations engine for controlled financial workflows.**

ApexOperator is built around one core idea:

> **Let AI reason about work, but never let AI alone authorize financial consequences.**

The system separates planning from governed execution:

`AI Planner → Tool Registry → RBAC → Deterministic Policy → Human Gate → Execution → Persistent Cryptographic Audit`

## Why this project matters

Most agent demos stop at “the model called a tool.” ApexOperator focuses on the harder engineering problem: **how an agent can operate in a sensitive workflow while remaining bounded, observable, auditable, and safe to interrupt.**

The project demonstrates:

- Decimal-safe financial models and deterministic policy enforcement.
- Server-resolved RBAC with explicit permissions.
- A central Tool Registry that governs tool execution.
- Bounded planning with retry and step limits.
- Real human approval and rejection workflow.
- Playwright browser automation with deterministic selector fallbacks and post-action verification.
- PDF invoice extraction with confidence classification and a provider-neutral OCR boundary.
- SQLite/PostgreSQL persistence through SQLAlchemy.
- A tamper-evident SHA-256 audit chain.
- Adversarial security and evaluation tests.
- Structured JSON request logging and readiness checks.

## Current build status

**Phase 0 — Foundation: ✅ locked**  
**Phase 1 — Persistent audit: ✅ locked**  
**Phase 2 — Agent runtime + RBAC: ✅ locked**  
**Phase 3 — FastAPI + human approval API: ✅ locked**  
**Phase 4 — Playwright browser automation: ✅ locked**  
**Phase 5 — Security evaluation: ✅ locked**  
**Phase 6 — Document intelligence: ✅ locked**  
**Phase 7 — Production persistence + dashboard: ✅ locked**

Every phase was merged only after GitHub Actions verification.

## Architecture

```text
                    ┌───────────────────────┐
                    │      AI Planner       │
                    │  intent + tool plan   │
                    └───────────┬───────────┘
                                ↓
                    ┌───────────────────────┐
                    │     Agent Runtime     │
                    │ bounded steps/retries │
                    └───────────┬───────────┘
                                ↓
                    ┌───────────────────────┐
                    │     Tool Registry     │
                    │ typed + centrally     │
                    │ governed execution    │
                    └───────────┬───────────┘
                                ↓
                    ┌───────────────────────┐
                    │         RBAC          │
                    │ role → permission     │
                    └───────────┬───────────┘
                                ↓
                    ┌───────────────────────┐
                    │ Deterministic Policy  │
                    │ math + thresholds     │
                    └───────────┬───────────┘
                                ↓
                 ┌──────────────┴───────────────┐
                 ↓                              ↓
      ┌────────────────────┐          ┌─────────────────────┐
      │ Human Approval Gate│          │ Deterministic       │
      │ approve / reject   │          │ recovery / failure  │
      └──────────┬─────────┘          └──────────┬──────────┘
                 └──────────────┬───────────────┘
                                ↓
                    ┌───────────────────────┐
                    │ Execution             │
                    │ API / browser / docs  │
                    └───────────┬───────────┘
                                ↓
                    ┌───────────────────────┐
                    │ Persistent Audit      │
                    │ SHA-256 hash chain    │
                    └───────────────────────┘
```

## Safety boundary

ApexOperator intentionally does **not** treat the LLM as a trusted authorization layer.

The LLM may propose:

- what the user wants;
- which governed tool could help;
- how an exception could be explained or recovered.

Deterministic application code decides:

- financial calculations;
- invoice consistency;
- authorization;
- approval thresholds;
- state transitions;
- retry/step limits;
- audit persistence and verification.

## Two-minute demo

The fastest demo path is:

1. Start the API.
2. Submit a low-value invoice and show **AUTO_APPROVED**.
3. Submit a high-value invoice and show **PENDING_HUMAN_APPROVAL**.
4. Approve that exact pending task as a finance manager.
5. Open the dashboard.
6. Run `/audit/verify` and show the audit chain is valid.

See **[docs/DEMO.md](docs/DEMO.md)** for the exact commands.

## Frontend experience

ApexOperator includes a recruiter-facing product surface as well as the backend control plane.

The frontend is intentionally designed around the same engineering story as the backend:
- a polished product landing experience;
- a live operations control room backed by the FastAPI task and audit APIs;
- visible trust-boundary messaging rather than generic AI magic;
- responsive layouts for desktop and mobile;
- clear workflow states, risk cues, audit health, loading states, and action feedback;
- local demo authentication with no claim of production identity infrastructure.

Start the API and open `http://127.0.0.1:8000/` to see the product surface. The landing page can launch the live control room and connect to the development tokens.
## Local development

Python 3.11+ is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Start the API:

```bash
uvicorn apexoperator.api.main:create_app --factory --reload
```

Open **http://127.0.0.1:8000/** for the product landing page and live control room.

```
```

The development authentication mapping is intentionally local-only. It is not presented as production identity infrastructure.

## Evidence

- **Architecture:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Engineering case study:** [docs/CASE_STUDY.md](docs/CASE_STUDY.md)
- **Demo script:** [docs/DEMO.md](docs/DEMO.md)
- **Security model:** [docs/SECURITY.md](docs/SECURITY.md)
- **Resume bullets:** [docs/RESUME.md](docs/RESUME.md)
- **Interview guide:** [docs/INTERVIEW.md](docs/INTERVIEW.md)

## Engineering principles

- LLM output is untrusted.
- Financial values use Decimal-safe representations.
- Authorization is deterministic and server-side.
- Tool execution is centrally governed.
- Human approvals are tied to real pending state.
- Browser actions require post-action verification.
- Audit integrity is cryptographically verifiable.
- Tests and CI are the source of truth.
