# ApexOperator — Engineering Case Study

## Problem

Financial operations contain repetitive work—reading invoices, validating totals, routing approvals, and updating external systems—but the consequences of an incorrect action can be expensive.

A naive autonomous agent can reason well and still be unsafe because the model itself is not a sufficient authorization boundary.

## Goal

Build an agentic operations engine where AI can plan useful work without being trusted to decide whether a financially consequential action is allowed.

## Design decision

The project uses a layered control path:

`AI Planner → Tool Registry → RBAC → Deterministic Policy → Human Gate → Execution → Audit`

This turns “agent autonomy” into **bounded autonomy**.

## What was implemented

### Financial correctness

Money is represented with `Decimal`, native float inputs are rejected, negative monetary values are blocked, and invoice totals are verified deterministically.

### Authorization

Every governed tool declares a required permission. Roles are resolved on the server side and checked before handlers execute.

### Human control

Invoices above the automatic threshold create real pending tasks. Approval/rejection endpoints operate on those persisted states instead of simply logging a decision.

### External execution

Playwright can interact with a deterministic local portal fixture using selector fallback chains. Submission is not considered successful until the resulting page state is verified.

### Document ingestion

PDF invoices can be parsed into structured fields. An OCR provider can be injected at the interface boundary. Unsafe filenames, path traversal, and MIME/magic mismatches are rejected.

### Persistence and auditability

Task state and the cryptographic audit chain can be persisted through SQLAlchemy-backed SQLite or PostgreSQL.

### Evaluation

The test suite deliberately attacks the control plane:

- unauthorized permissions;
- audit payload tampering;
- duplicate event IDs;
- invalid state transitions;
- deletion/insertion/reordering of persistent audit data;
- bounded runtime failures.

## Engineering lessons

### 1. Autonomy needs a governor

The runtime is deliberately not the final authority. A planner can request a tool, but the registry and RBAC layer still decide whether that call is permitted.

### 2. Human approval should be stateful

A “human approved” log entry is not enough. The approval endpoint must correspond to an actual pending escalation and transition that state safely.

### 3. Browser automation needs verification

A click succeeding at the DOM level is not the same thing as a business action succeeding. ApexOperator verifies the resulting portal state.

### 4. Auditability must include the failure paths

Denied tool calls and failed tool execution are also operationally important. They should not disappear just because no business action was completed.

### 5. CI is part of the engineering design

The project uses GitHub Actions as an implementation gate. Real CI failures led to fixes in browser provisioning, persistence/thread handling, document parsing, and cross-backend audit compatibility.

## Result

The finished system is a compact reference implementation for controlled agentic operations:

- agent reasoning;
- deterministic controls;
- external execution;
- human intervention;
- persistent state;
- cryptographic tamper evidence;
- adversarial evaluation.

It is intentionally presented as a production-oriented engineering foundation, not as a claim of complete enterprise compliance or unrestricted autonomous operation.
