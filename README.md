# ApexOperator

A production-oriented autonomous business operations engine for controlled financial workflows.

ApexOperator separates AI planning from deterministic authorization and execution:

`AI Planner → Tool Registry → RBAC → Deterministic Policy → Human Gate → Execution → Cryptographic Audit`

## Current status

**Phase 0 — Foundation: locked after successful CI.**  
**Phase 1 — Persistent audit: locked after successful CI.**  
**Phase 2 — Agent runtime + RBAC: locked after successful CI.**  
**Phase 3 — FastAPI + human approval API: locked after successful CI.**  
**Phase 4 — Playwright browser automation: locked after successful CI.**  
**Phase 5 — Security evaluation: locked after successful CI.**  
**Phase 6 — Document intelligence: locked after successful CI.**  
**Phase 7 — Production persistence + dashboard: implementation on branch `phase7-production-postgres`; CI verification is required before phase lock.**

This repository is the source of truth. Historical design reports and generated prompts are treated as specifications, not as proof of implementation.

## Implemented capabilities

- Decimal-safe invoice domain model and deterministic policy enforcement.
- Persistent SQLite and SQLAlchemy-backed database stores.
- Cryptographic audit chains with duplicate-event protection and tamper detection.
- Server-resolved RBAC and a governed Tool Registry.
- Bounded Agent Runtime with deterministic retry limits.
- FastAPI task workflow with explicit human approval/rejection.
- Playwright browser automation with selector fallbacks and post-action verification.
- PDF invoice extraction, confidence classification, and provider-neutral OCR boundary.
- PostgreSQL persistence path with CI integration coverage.
- Secured operational dashboard and readiness endpoint.
- Adversarial security/evaluation tests.

## Engineering principles

- LLM output is untrusted and never acts as an authorization boundary.
- Financial calculations use deterministic application logic and Decimal-safe values.
- Sensitive tool execution passes through a governed registry and RBAC.
- Human approval is explicit for policy-defined exceptions.
- Execution is bounded and auditable.
- Browser automation requires post-action verification.
- Audit integrity is cryptographically verifiable.
- Tests and CI are the source of truth for implementation status.

## Development

Python 3.11+ is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Run the API locally:

```bash
uvicorn apexoperator.api.main:create_app --factory --reload
```

A phase is considered complete only when its implementation exists in this repository and its tests execute successfully in CI.
