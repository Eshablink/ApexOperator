# ApexOperator — Interview Guide

## 30-second answer

“ApexOperator is an agentic finance operations engine I built around a simple safety boundary: the LLM can reason and propose a plan, but it cannot authorize financial consequences. Tool calls pass through a central registry, RBAC, deterministic policy checks, and bounded execution. Higher-risk work becomes a real human approval state, external browser actions are verified after execution, and consequential events are stored in a tamper-evident audit chain.”

## 60-second architecture answer

“The flow is AI Planner → Agent Runtime → Tool Registry → RBAC → Deterministic Policy → Human Gate or Execution → Verification → Persistent Audit. I deliberately separated probabilistic reasoning from deterministic authority. The model is useful for intent understanding, extraction, planning, and exception explanations. The application owns money calculations, permissions, approval thresholds, state transitions, retry limits, and audit integrity. That makes the agent useful without making the model the security boundary.”

## Two-minute project walkthrough

Start with the problem:

“Finance operations contain repetitive invoice work, but automation becomes risky when an AI system can directly trigger consequential actions.”

Then explain the design:

“I designed ApexOperator as a governed digital worker. The agent can propose what to do, but every meaningful action is converted into a typed tool call. The Tool Registry checks the caller’s server-resolved role and permissions before the handler can run. Invoice money uses Decimal, and deterministic policy checks the calculated total and threshold. In this reference workflow, invoices at or below 5000 are auto-approved when consistent; higher values require human approval; inconsistent totals are rejected.”

Then show the interesting control points:

“For risky work, the system creates a persisted PENDING_HUMAN_APPROVAL state. A finance manager must approve that exact task, so approval is not just a UI action—it is a state transition enforced by the backend. For browser automation, Playwright uses deterministic selector fallbacks and verifies the resulting portal state after submission. For documents, PDF extraction validates file type and paths and exposes confidence plus an OCR provider boundary.”

Finish with evidence:

“Finally, every consequential operation is auditable. The audit ledger uses SHA-256 chaining so tampering with payloads, sequence, deletion, or insertion is detectable. I also used GitHub Actions as a merge gate, including PostgreSQL integration coverage. The key engineering principle is: **AI handles ambiguity; deterministic software handles authority.**”

## High-value interview questions

### Why not let the LLM decide whether to approve an invoice?

Because approval is an authorization decision, not a language-understanding problem. The LLM can recommend or classify, but deterministic application code must enforce the financial rule consistently and testably.

### Why use a Tool Registry?

It creates one governed execution boundary. Instead of trusting every agent-generated function call, tools have typed contracts, explicit permissions, centralized auditing, and a predictable execution path.

### Why RBAC instead of prompting the model to behave?

Prompting is not an authorization mechanism. Permissions need to be resolved and enforced by trusted server-side code before the handler executes.

### Why have both policy and RBAC?

They solve different problems. RBAC answers **“is this actor allowed to perform this capability?”** Deterministic policy answers **“under these business rules, is this specific operation allowed, rejected, or escalated?”**

### How does the human approval gate work?

The backend persists a pending state. Approval and rejection endpoints target that exact task, enforce the manager permission, audit the attempted decision, and only then perform the valid state transition. Repeated or invalid transitions are rejected.

### What happens when browser automation fails?

The failure is surfaced through the governed Tool Registry and audited. The browser adapter also verifies the post-action state rather than treating a click or navigation as proof of success.

### Why is the audit ledger called tamper-evident?

The hash chain makes unauthorized modification detectable, but it does not make the underlying database physically immutable. True immutability would require stronger infrastructure controls.

### What security tests did you prioritize?

Authorization matrix checks, handler non-execution on denial, malformed tool input, invalid state transitions, runtime bounds, audit-chain tampering, duplicate event IDs, persistent deletion/insertion/reordering, document path validation, and browser post-action failures.

### Why PostgreSQL if SQLite already works?

SQLite is convenient for local development and tests. SQLAlchemy provides a path to PostgreSQL-backed persistence for a more production-like deployment while keeping the application boundary clean.

### What would you add for a real production deployment?

A real identity provider, TLS, secret management, rate limiting, centralized observability, durable externalized audit storage, operational alerting, stronger deployment controls, and a real OCR/provider integration. I would add those deliberately rather than hiding them behind “enterprise-ready” claims.

## Three architecture phrases to remember

> **AI handles ambiguity. Deterministic software handles authority.**

> **The Tool Registry is the execution choke point.**

> **Human approval is a persisted state transition, not a UI decoration.**
