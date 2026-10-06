# ApexOperator Architecture

## 1. System boundary

ApexOperator is a controlled execution system, not a free-running chatbot.

The core boundary is:

`reason → govern → execute → observe → recover/escalate → verify → audit`

The model is allowed to operate only through typed, registered tools. Financial authorization and state transitions remain deterministic.

## 2. Major components

### Agent Runtime

The runtime executes bounded plans. The current implementation enforces a maximum step count and retry count so a faulty or adversarial plan cannot run indefinitely.

### Tool Registry

Every sensitive capability is represented as a registered tool with:

- a name;
- a typed input schema;
- a required permission;
- a handler.

The registry is the central execution path for governed tools and records execution outcomes.

### RBAC

Roles are mapped server-side to explicit permissions:

- **AP_CLERK**
- **FINANCE_MANAGER**
- **SYSTEM_ADMIN**

The permission set covers invoice access, validation, recalculation, approval actions, discrepancy escalation, audit access, and system administration.

### Deterministic Policy Engine

The policy layer validates financial consistency and approval thresholds. Monetary calculations use `Decimal`.

The current boundary is:

- `≤ 5000.00` → auto approval when mathematically consistent;
- `> 5000.00` → human escalation;
- inconsistent totals → rejection.

### Human Approval Service

Escalations become real persisted tasks.

An approve/reject request must target a task whose current state is `PENDING_HUMAN_APPROVAL`. State transition uses a conditional update so a second reviewer cannot re-approve an already completed task.

### Browser Automation

Playwright is isolated behind a portal adapter.

The adapter uses deterministic selector fallback chains, bounded timeouts, and explicit post-submit verification.

Browser automation does not bypass RBAC or policy enforcement.

### Document Intelligence

PDF documents are parsed through PyMuPDF. Structured monetary fields are normalized into `Decimal`.

OCR is represented as a provider-neutral interface so a deployment can attach an implementation without coupling the core architecture to a vendor.

A confidence threshold of `0.85` separates high-confidence extraction from review-required extraction.

### Persistence

SQLAlchemy provides the application persistence boundary.

The same model layer supports:

- SQLite for local development;
- PostgreSQL for integration/production-style deployment.

### Audit Ledger

The audit layer is an append-oriented hash chain.

Each event contains:

`sequence_id + timestamp + event_id + type + action + state + previous_hash`

The event hash is calculated from canonicalized data. The stored chain head makes deletion of the tail detectable.

This is **tamper-evidence**, not a claim of physically immutable storage.

### Observability

HTTP requests are emitted as structured JSON logs. A readiness endpoint verifies both persistence access and audit integrity before returning ready.

## 3. Trust model

### Trusted

- deterministic application code;
- RBAC mappings;
- policy engine;
- persistence constraints;
- audit verification;
- server-resolved principal.

### Untrusted

- LLM-generated plans;
- extracted document text;
- browser page contents;
- client-provided request bodies.

The system validates or constrains untrusted data before it reaches a consequential boundary.

## 4. Failure handling

ApexOperator prefers bounded failure over silent success.

Examples:

- invalid tool input → rejected and audited;
- unauthorized tool call → denied and audited;
- repeated runtime failure → retry limit reached;
- browser submission mismatch → post-action verification failure;
- invoice mismatch → deterministic rejection;
- uncertain document extraction → review boundary.

## 5. Why the architecture is portfolio-worthy

The interesting part is not the number of frameworks. It is the separation of responsibilities:

**AI handles ambiguity. Deterministic software handles authority.**

That makes the project useful for demonstrating agent engineering, backend systems design, security thinking, and production-oriented software boundaries in one coherent system.
