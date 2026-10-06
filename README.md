# ApexOperator

A production-oriented autonomous business operations engine for controlled financial workflows.

ApexOperator separates AI planning from deterministic authorization and execution:

`AI Planner → Tool Registry → RBAC → Deterministic Policy → Human Gate → Execution → Cryptographic Audit`

## Current status

Phase 0 foundation is being established directly in this repository. Subsequent phases will be implemented only when their source code and tests are committed here.

## Engineering principles

- LLM output is untrusted and never acts as an authorization boundary.
- Financial calculations use deterministic application logic and Decimal-safe values.
- Sensitive tool execution passes through a governed registry and RBAC.
- Human approval is explicit for policy-defined exceptions.
- Execution is bounded and auditable.
- Audit integrity is cryptographically verifiable.
- Tests and CI are the source of truth for implementation status.

## Planned capabilities

- Deterministic invoice policy evaluation
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

Python 3.11+ is recommended.

Run tests with:

```bash
pytest -q
```

## Status discipline

A phase is considered complete only when its implementation exists in this repository and its tests execute successfully in CI. Historical design reports are treated as specifications, not as proof of implementation.
