# Recruiter-Ready Resume Content

Use these bullets under **Projects — ApexOperator**. Keep 3–4 bullets on the final resume.

## Recommended 4 bullets

- Built **ApexOperator**, a production-oriented agentic operations engine for controlled financial workflows, separating LLM planning from deterministic authorization, policy enforcement, and execution.
- Implemented a governed **Tool Registry + RBAC layer** with typed inputs, centralized permission checks, bounded agent steps/retries, explicit human approval gates, and audited tool outcomes.
- Built a tamper-evident **SHA-256 audit chain** with SQLite and SQLAlchemy-backed persistence, plus PostgreSQL integration coverage and verification against deletion, insertion, reordering, and payload tampering.
- Added **Playwright browser automation, PDF invoice extraction, security evaluation, FastAPI APIs, and a recruiter-facing dashboard**, with post-action verification and CI-gated phase merges.

## Backend / AI-focused version

- Engineered an agentic finance workflow using **Python, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Playwright, and deterministic policy controls**, keeping LLM output outside the authorization boundary.
- Designed a central Tool Registry that enforces **server-side RBAC, typed validation, retry/step bounds, audit logging, and controlled execution** across invoice operations.
- Implemented persistent, tamper-evident **SHA-256 audit logging** and adversarial tests for authorization failures, state-transition violations, and audit-chain tampering.
- Added document intelligence for **PDF invoice extraction**, confidence classification, secure file validation, and a provider-neutral OCR interface.

## One-line project entry

**ApexOperator — Agentic Finance Operations Engine | Python, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Playwright, PyMuPDF, pytest**

## Accuracy guardrails

Do not describe this project as:
- fully autonomous;
- SOC 2/GDPR/PCI compliant;
- production identity infrastructure;
- physically immutable audit storage;
- production OCR with a specific external provider unless separately integrated.

Use phrases such as **production-oriented**, **controlled**, **bounded**, **tamper-evident**, and **reference implementation**.
