# ⚡ ApexOperator

[![CI](https://github.com/Eshablink/ApexOperator/actions/workflows/ci.yml/badge.svg)](https://github.com/Eshablink/ApexOperator/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Playwright](https://img.shields.io/badge/Playwright-1.50%2B-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **ApexOperator is a production-oriented agentic operations engine for controlled financial workflows.**
>
> **AI handles ambiguity. Deterministic software handles authority.**

[**Live demo →**](https://apexoperator.onrender.com) · [**Architecture**](docs/ARCHITECTURE.md) · [**Security model**](docs/SECURITY.md) · [**Demo guide**](docs/DEMO.md)

---

## What ApexOperator is

ApexOperator is a **governed execution system**, not a free-running chatbot.

It takes an operational request, lets an AI planner propose the next step, and then forces every consequential action through deterministic controls:

~~~text
Request
  ↓
AI Planner
  ↓
Bounded Agent Runtime
  ↓
Typed Tool Registry
  ↓
Server-side RBAC
  ↓
Deterministic Financial Policy
  ↓
Human Approval Gate (when required)
  ↓
Execution + Post-action Verification
  ↓
Persistent Audit + Integrity Verification
~~~

The key design choice is deliberate: **the LLM never becomes the authorization boundary.**

### What the model can do

- understand intent;
- propose a governed tool/action;
- help explain or recover from an exception.

### What application code must decide

- financial calculations;
- invoice consistency;
- authorization and permissions;
- approval thresholds;
- workflow state transitions;
- retry/step limits;
- persistence;
- audit integrity.

---

## Why this is interesting

A lot of agent demos prove that an LLM can call a tool.

ApexOperator focuses on the next problem:

> **How do you let an agent operate in a high-consequence workflow without giving the model uncontrolled authority?**

| Capability | Implementation |
|---|---|
| Agent planning | Deterministic mock planner + optional OpenAI Responses API planner |
| Runtime safety | Bounded step/retry execution with workflow-state validation |
| Tool governance | Central typed Tool Registry |
| Authorization | Server-resolved RBAC |
| Financial policy | Decimal-safe calculations + deterministic thresholds |
| Human oversight | Persisted approve/reject workflow |
| Browser automation | Playwright adapter + selector fallbacks + post-action verification |
| Document intelligence | PyMuPDF extraction + confidence boundary + OCR interface |
| Persistence | SQLAlchemy with SQLite locally and PostgreSQL for deployment |
| Auditability | SHA-256 chained audit ledger |
| Observability | Structured JSON HTTP logging + readiness checks |
| Web application | FastAPI + responsive recruiter-facing control room |
| Deployment | Docker + Render Web Service + Render PostgreSQL |

---

## 🏗️ Architecture

~~~mermaid
flowchart LR
    A[User / API Request] --> B[AI Planner]
    B --> C[Bounded Agent Runtime]
    C --> D[Tool Registry]
    D --> E[Server-side RBAC]
    E --> F[Deterministic Policy]

    F -->|Auto-approved| G[Execution]
    F -->|Threshold exceeded| H[Human Approval]
    F -->|Mismatch| I[Reject]

    H -->|Approve| G
    H -->|Reject| I

    G --> J[Post-action Verification]
    I --> K[Persisted Task State]
    J --> K

    K --> L[(SQLite / PostgreSQL)]
    J --> M[SHA-256 Audit Ledger]
    K --> M
~~~

### Trust boundary

~~~text
                    UNTRUSTED
       ┌──────────────────────────────┐
       │ LLM output                   │
       │ PDF / document text          │
       │ Browser page content         │
       │ Client request bodies        │
       └──────────────┬───────────────┘
                      │ validate / constrain
                      ▼
              TRUSTED APPLICATION
       ┌──────────────────────────────┐
       │ RBAC                         │
       │ Policy Engine                │
       │ Workflow State               │
       │ Step / Retry Bounds          │
       │ Persistence                  │
       │ Audit Verification           │
       └──────────────────────────────┘
~~~

Read the deeper design rationale in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 💡 Core workflow

ApexOperator currently models invoice operations with a deterministic financial boundary:

| Condition | Outcome |
|---|---|
| Mathematically consistent and ≤ ₹5,000 | AUTO_APPROVED |
| Mathematically consistent and > ₹5,000 | PENDING_HUMAN_APPROVAL |
| Inconsistent invoice total | REJECTED |

A pending task is a **real persisted state**, not a UI placeholder. A reviewer can approve or reject the exact task, and the transition is conditional on the task still being pending.

---

## 🎛️ Product surface

The project includes a recruiter-facing product experience rather than only an API.

### Landing experience

- clear product positioning;
- visible AI-vs-deterministic trust boundary;
- architecture storytelling;
- live product preview;
- direct launch into the control room.

### Operations control room

- live task KPIs with cold-start/wake-up messaging;
- search, status filters and server-side pagination;
- one-click development demo role access;
- task detail view with AI planner proposals, policy decision and audit timeline;
- approve/reject with a mandatory reviewer reason and conditional state transition;
- tamper simulation followed by cryptographic audit verification;
- CSV/JSON audit export and demo-data reset controls;
- planner mode selection with deterministic mock fallback and optional OpenAI planner;
- audit-integrity indicator and planner/runtime status;
- quick invoice processing;
- explicit loading, empty, error and retry states;
- responsive mobile operations cards and bottom navigation.

### 2026 UX layer

The latest product pass adds:

- secure-session status in the shell;
- production login surface;
- keyboard-first command palette with Ctrl/Cmd + K;
- visible keyboard focus states;
- reduced-motion support;
- high-signal status/risk treatments;
- responsive layouts that preserve task density without feeling like a legacy admin panel.

---

## 🔐 Security model

ApexOperator intentionally treats the LLM as **untrusted reasoning output**.

Production authentication uses:

- database-backed users;
- scrypt password verification;
- signed HS256 JWTs;
- revocable database sessions;
- HttpOnly + Secure + SameSite cookies;
- CSRF protection on state-changing requests;
- deterministic server-side RBAC.

Production startup fails closed unless the deployment provides a persistent database, a strong JWT secret, and bootstrap identity configuration.

The local development role picker is available only outside APP_ENV=production.

See [docs/SECURITY.md](docs/SECURITY.md).

---

## 🤖 Planner modes

ApexOperator supports two planner modes.

### mock

Deterministic local planning for:

- zero-credential demos;
- repeatable tests;
- CI;
- safe portfolio demonstrations.

### openai

Optional OpenAI-backed planning using structured output.

~~~bash
APEX_PLANNER=openai
OPENAI_API_KEY=<your-key>
OPENAI_MODEL=<your-model>
~~~

The model still cannot bypass the runtime, Tool Registry, RBAC, policy engine, state machine, or audit layer.

---

## 🚀 Quick start

### Prerequisites

- Python 3.11+
- Git
- Optional Docker for the full containerized reference stack

### Local setup

~~~bash
git clone https://github.com/Eshablink/ApexOperator.git
cd ApexOperator

python -m venv .venv
~~~

Activate the environment.

**macOS / Linux**

~~~bash
source .venv/bin/activate
~~~

**Windows PowerShell**

~~~powershell
.venv\Scripts\Activate.ps1
~~~

Install:

~~~bash
pip install -e ".[dev]"
~~~

Run the test suite:

~~~bash
pytest
~~~

Start the product:

~~~bash
uvicorn apexoperator.api.main:create_app --factory --reload
~~~

Open:

~~~text
http://127.0.0.1:8000/
~~~

---

## 🎬 Two-minute demo

The repository includes a deterministic demo script:

~~~bash
PYTHONPATH=src python scripts/demo.py
~~~

Expected flow:

~~~text
LOW invoice
  → AUTO_APPROVED

HIGH invoice
  → PENDING_HUMAN_APPROVAL

Finance manager approval
  → APPROVED

Audit verification
  → integrity_valid = true
~~~

For the complete walkthrough, see [docs/DEMO.md](docs/DEMO.md).

---

## 🔌 Minimal API usage

ApexOperator is exposed through FastAPI.

~~~bash
curl -X POST http://127.0.0.1:8000/tasks \
  -H "Authorization: Bearer dev-clerk-token" \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "INV-LOW-001",
    "justification": "Routine processing"
  }'
~~~

Useful endpoints:

| Endpoint | Purpose |
|---|---|
| GET / | Product landing surface |
| GET /health | Liveness |
| GET /ready | Readiness + persistence/audit checks |
| GET /dashboard | Control-room application |
| GET /dashboard/data | Live dashboard data |
| POST /tasks | Start governed invoice workflow |
| GET /tasks/{task_id} | Inspect persisted task |
| POST /tasks/{task_id}/approve | Human approval |
| POST /tasks/{task_id}/reject | Human rejection |
| GET /audit/verify | Verify audit integrity |
| POST /auth/login | Production login |
| POST /auth/logout | Production logout |

---

## ⚙️ Configuration

### Development / demo

| Variable | Default | Purpose |
|---|---|---|
| APP_ENV | development | Application environment |
| LOG_LEVEL | INFO | Structured logging level |
| DATABASE_URL | sqlite:///./apexoperator.db | Local persistence |
| APEX_PLANNER | mock | Planner mode |
| OPENAI_API_KEY | empty | Optional live planner credential |
| OPENAI_MODEL | configured in settings | OpenAI planner model |

### Production

| Variable | Required | Purpose |
|---|---:|---|
| APP_ENV | Yes | Set to production |
| DATABASE_URL | Yes | Persistent PostgreSQL connection |
| JWT_SECRET | Yes | 32+ character signing secret |
| APEX_BOOTSTRAP_EMAIL | Yes | First operator account |
| APEX_BOOTSTRAP_PASSWORD_HASH | Yes | scrypt password hash |
| APEX_BOOTSTRAP_ROLE | Yes | AP_CLERK, FINANCE_MANAGER, or SYSTEM_ADMIN |
| APEX_SESSION_MINUTES | No | Session lifetime; default 60 |
| JWT_ISSUER | No | Optional issuer validation |
| JWT_AUDIENCE | No | Optional audience validation |
| APEX_PLANNER | Yes | mock or openai |
| OPENAI_API_KEY | Only for openai | LLM provider credential |
| OPENAI_MODEL | Only for openai | LLM model |

Generate a bootstrap password hash locally:

~~~bash
PYTHONPATH=src python scripts/make_password_hash.py
~~~

Never commit credentials to the repository.

---

## ☁️ Deployment

ApexOperator has a Docker-based Render reference deployment:

~~~text
GitHub main
   ↓
Render Web Service
   ↓
Docker image
   ↓
FastAPI application
   ↓
Render PostgreSQL
~~~

The live reference service is available at:

**https://apexoperator.onrender.com**

### Render environment

For actual production authentication, configure:

~~~text
APP_ENV=production
DATABASE_URL=<Render internal PostgreSQL URL>
JWT_SECRET=<random 32+ character secret>
APEX_BOOTSTRAP_EMAIL=<operator email>
APEX_BOOTSTRAP_PASSWORD_HASH=<scrypt hash>
APEX_BOOTSTRAP_ROLE=FINANCE_MANAGER
APEX_SESSION_MINUTES=60
~~~

The hosted reference/demo can remain in development/demo auth mode until real operator credentials are provisioned.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## 🧪 Testing & verification

The repository includes coverage for:

- foundation/domain validation;
- bounded runtime behavior;
- RBAC and permission checks;
- FastAPI endpoints;
- browser automation;
- security evaluation;
- document extraction;
- persistence;
- PostgreSQL integration;
- audit integrity;
- live-planner behavior;
- frontend/API behavior;
- production authentication;
- revocable sessions;
- CSRF behavior;
- restart/reinitialization persistence.

Run locally:

~~~bash
pytest
~~~

GitHub Actions is the source of truth for the repository merge gate.

---

## 🧭 Engineering principles

1. **LLM output is untrusted.**
2. **Authority is deterministic.**
3. **Financial values use Decimal-safe representations.**
4. **Every sensitive capability passes through a governed tool path.**
5. **High-consequence actions can pause for human approval.**
6. **External side effects require post-action verification.**
7. **Audit integrity is cryptographically verifiable.**
8. **Tests and CI outrank optimistic documentation.**

---

## 📚 Documentation

| Document | Purpose |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | System boundaries and component design |
| [Security](docs/SECURITY.md) | Threat model and production security boundary |
| [Deployment](docs/DEPLOYMENT.md) | Render + production configuration |
| [Demo](docs/DEMO.md) | End-to-end portfolio demo |
| [Case Study](docs/CASE_STUDY.md) | Engineering narrative |
| [Interview Guide](docs/INTERVIEW.md) | Technical discussion prompts |

---

## 🤝 Contributing

Pull requests are welcome.

Before opening a PR:

~~~bash
pip install -e ".[dev]"
pytest
~~~

For architecture changes, update the relevant documentation alongside the implementation.

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

<p align="center">
  <strong>ApexOperator</strong><br>
  <sub>Reason with AI. Govern with code. Execute with evidence.</sub>
</p>
