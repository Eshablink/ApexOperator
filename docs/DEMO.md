# ApexOperator Demo

## 0. Frontend-first demo

Open `http://127.0.0.1:8000/` after starting the API. The product landing page is the primary presentation surface.

Click **Open live control room** and choose **Finance Manager**. The control room exposes live persisted task data, audit integrity, planner mode, runtime bounds, invoice processing, and explicit approve/reject actions.

## Optional live AI planner

Set `APEX_PLANNER=openai`, `OPENAI_API_KEY`, and optionally `OPENAI_MODEL` before starting the API.

The same approval workflow remains governed by the deterministic runtime and Tool Registry. The LLM only proposes the next permitted action.

## Container demo

```bash
docker compose up --build
```

Then open `http://127.0.0.1:8000/`.

This demo is designed to fit into roughly two minutes.

## 1. Start the API

```bash
uvicorn apexoperator.api.main:create_app --factory --reload
```

Open:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/dashboard`

Development tokens are defined in the application factory:

- `dev-clerk-token`
- `dev-manager-token`
- `dev-admin-token`

## 2. Show automatic approval

```bash
curl -X POST http://127.0.0.1:8000/tasks ^
  -H "Authorization: Bearer dev-clerk-token" ^
  -H "Content-Type: application/json" ^
  -d "{"invoice_id":"INV-LOW-001"}"
```

Expected:

`status = AUTO_APPROVED`

## 3. Show the human gate

```bash
curl -X POST http://127.0.0.1:8000/tasks ^
  -H "Authorization: Bearer dev-clerk-token" ^
  -H "Content-Type: application/json" ^
  -d "{"invoice_id":"INV-HIGH-001","justification":"Threshold exceeded"}"
```

Expected:

`status = PENDING_HUMAN_APPROVAL`

This is a real persisted task, not a simulated message.

## 4. Approve the exact pending task

Copy the returned `task_id`:

```bash
curl -X POST http://127.0.0.1:8000/tasks/<TASK_ID>/approve ^
  -H "Authorization: Bearer dev-manager-token" ^
  -H "Content-Type: application/json" ^
  -d "{"comment":"Verified by finance manager"}"
```

Expected:

`status = APPROVED`

A clerk token should receive `403 permission denied`.

## 5. Verify the audit trail

```bash
curl http://127.0.0.1:8000/audit/verify ^
  -H "Authorization: Bearer dev-manager-token"
```

Expected:

```json
{"integrity_valid":true}
```

## 6. Open the dashboard

`http://127.0.0.1:8000/dashboard`

Use a finance-manager token in the request.

The dashboard shows the approval/task queue and current audit integrity.

## Recruiter narration

> “ApexOperator is an agentic finance operations engine. The model can plan work, but it cannot authorize money movement by itself. Tool calls go through RBAC and deterministic policy, escalations become persisted human gates, browser actions are verified after execution, and every consequential step is auditable through a cryptographic chain. I built the system phase by phase and used CI as the merge gate.”

## Demo focus

Spend the most time on the **control boundary**, not on the number of libraries.

The strongest story is:

**agent proposes → policy governs → human intervenes when required → execution verifies → audit proves what happened.**
