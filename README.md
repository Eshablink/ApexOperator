# ApexOperator

A production-oriented autonomous business operations engine for controlled financial workflows.

ApexOperator separates AI planning from deterministic authorization and execution:

`AI Planner → Tool Registry → RBAC → Deterministic Policy → Human Gate → Execution → Cryptographic Audit`

## Current status

**Phase 0 — Foundation: implementation complete on branch `phase0-hardening`; CI verification is required before merge/phase lock.**

This repository is the source of truth. Historical design reports and generated prompts are treated as specifications, not as proof of implementation.

## Phase 0 scope

- Installable Python package using a `src/apexoperator` layout.
- Decimal-safe invoice domain model with rejection of native floats for money.
- Deterministic invoice policy with exact `5000.00` auto-approval boundary.
- Cryptographic SHA-256 audit chain with genesis linkage, event IDs, canonical payload hashing, and tamper detection.
- Pytest coverage for boundary, validation, and audit-integrity cases.
- GitHub Actions CI for Python 3.11.

## Engineering principles

- LLM output is untrusted and never acts as an authorization boundary.
- Financial calculations use deterministic application logic and Decimal-safe values.
- Sensitive tool execution passes through a governed registry and RBAC.
- Human approval is explicit for policy-defined exceptions.
- Execution is bounded and auditable.
- Audit integrity is cryptographically verifiable.
- Tests and CI are the source of truth for implementation status.

## Planned capabilities

- RBAC and governed tools
- Agent runtime with bounded execution
- FastAPI API and human approval workflow
- Playwright browser automation with bounded recovery
- PDF/OCR document intelligence
- PostgreSQL persistence
- Operations dashboard
- Security/adversarial evaluation
- Structured observability

## Development

Python 3.11+ is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

A phase is considered complete only when its implementation exists in this repository and its tests execute successfully in CI.
