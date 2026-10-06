from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from apexoperator.observability.logging import configure_logging, log_request

from apexoperator.api.schemas import (
    ApprovalRequest,
    AuditVerificationResponse,
    CreateTaskRequest,
    TaskResponse,
)
from apexoperator.persistence.database import init_database, make_engine, make_session_factory
from apexoperator.persistence.sqlalchemy_audit import SQLAlchemyAuditLedger
from apexoperator.persistence.sqlalchemy_tasks import SQLAlchemyTaskStore
from apexoperator.security.auth import InMemoryAuthenticator, Principal
from apexoperator.security.rbac import Permission, RBAC, Role
from apexoperator.service.approvals import ApprovalService


def create_app(
    *,
    workspace_dir: str | Path = "workspace",
    database_path: str | Path = "apexoperator_api.sqlite3",
    database_url: str | None = None,
    authenticator: InMemoryAuthenticator | None = None,
) -> FastAPI:
    authenticator = authenticator or InMemoryAuthenticator(
        {
            "dev-clerk-token": Principal("dev-clerk", Role.AP_CLERK),
            "dev-manager-token": Principal("dev-manager", Role.FINANCE_MANAGER),
            "dev-admin-token": Principal("dev-admin", Role.SYSTEM_ADMIN),
        }
    )

    resolved_url = database_url or f"sqlite:///{Path(database_path).resolve()}"
    engine = make_engine(resolved_url)
    init_database(engine)
    sessions = make_session_factory(engine)

    task_store = SQLAlchemyTaskStore(sessions)
    audit_ledger = SQLAlchemyAuditLedger(sessions)

    service = ApprovalService(
        workspace_dir=str(workspace_dir),
        task_store=task_store,
        audit_ledger=audit_ledger,
    )

    logger = configure_logging()
    api = FastAPI(title="ApexOperator API", version="0.2.0")
    api.state.authenticator = authenticator
    api.state.service = service
    api.state.engine = engine

    @api.middleware("http")
    async def request_logging(request: Request, call_next):
        started = __import__("time").perf_counter()
        response = await call_next(request)
        log_request(
            logger,
            request.method,
            request.url.path,
            response.status_code,
            (__import__("time").perf_counter() - started) * 1000,
        )
        return response

    def principal(request: Request) -> Principal:
        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="authorization required")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(status_code=401, detail="authorization required")
        return request.app.state.authenticator.authenticate(token)

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/ready")
    def ready(request: Request) -> dict[str, str]:
        try:
            request.app.state.service.task_store.list_recent(1)
            if not request.app.state.service.audit_ledger.verify_integrity():
                raise RuntimeError("audit integrity failure")
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"not ready: {type(exc).__name__}") from exc
        return {"status": "ready"}

    @api.post("/tasks", response_model=TaskResponse)
    def create_task(body: CreateTaskRequest, request: Request) -> TaskResponse:
        return request.app.state.service.create_task(body, principal(request))

    @api.get("/tasks/{task_id}", response_model=TaskResponse)
    def get_task(task_id: str, request: Request) -> TaskResponse:
        return request.app.state.service.get_task(task_id)

    @api.post("/tasks/{task_id}/approve", response_model=TaskResponse)
    def approve_task(task_id: str, body: ApprovalRequest, request: Request) -> TaskResponse:
        return request.app.state.service.review_task(task_id, body, principal(request), approve=True)

    @api.post("/tasks/{task_id}/reject", response_model=TaskResponse)
    def reject_task(task_id: str, body: ApprovalRequest, request: Request) -> TaskResponse:
        return request.app.state.service.review_task(task_id, body, principal(request), approve=False)

    @api.get("/audit/verify", response_model=AuditVerificationResponse)
    def verify_audit(request: Request) -> dict[str, bool]:
        return request.app.state.service.verify_audit(principal(request))

    @api.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        reviewer = principal(request)
        if not RBAC.is_allowed(reviewer.role, Permission.AUDIT_READ):
            raise HTTPException(status_code=403, detail="permission denied")

        from html import escape

        tasks = request.app.state.service.task_store.list_recent(50)
        audit_ok = request.app.state.service.audit_ledger.verify_integrity()

        counts = {}
        for task in tasks:
            counts[task["status"]] = counts.get(task["status"], 0) + 1

        pending = counts.get("PENDING_HUMAN_APPROVAL", 0)
        approved = counts.get("APPROVED", 0)
        rejected = counts.get("REJECTED", 0)
        auto_approved = counts.get("AUTO_APPROVED", 0)

        rows = "".join(
            "<tr>"
            f"<td><code>{escape(str(t['task_id']))}</code></td>"
            f"<td>{escape(str(t['invoice_id']))}</td>"
            f"<td><span class='status status-{escape(str(t['status']).lower())}'>{escape(str(t['status']))}</span></td>"
            f"<td>{escape(str(t['requested_by']))}</td>"
            f"<td>{escape(str(t['reviewer'] or '—'))}</td>"
            "</tr>"
            for t in tasks
        ) or "<tr><td colspan='5' class='empty'>No tasks yet</td></tr>"

        audit_label = "VALID" if audit_ok else "INVALID"
        audit_class = "ok" if audit_ok else "bad"

        html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ApexOperator • Operations Control Room</title>
<style>
:root {{
  color-scheme: light;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --ink:#111827; --muted:#6b7280; --line:#e5e7eb; --surface:#ffffff; --soft:#f8fafc;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; color:var(--ink); background:linear-gradient(180deg,#f8fafc 0%,#eef2ff 100%); min-height:100vh; }}
.shell {{ max-width:1180px; margin:0 auto; padding:42px 24px 56px; }}
.topbar {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-start; margin-bottom:28px; }}
.brand {{ letter-spacing:-.03em; }}
.eyebrow {{ color:#64748b; font-size:12px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }}
h1 {{ margin:6px 0 8px; font-size:32px; }}
.subtitle {{ margin:0; color:var(--muted); max-width:700px; line-height:1.6; }}
.audit {{ background:var(--surface); border:1px solid var(--line); border-radius:18px; padding:14px 18px; min-width:190px; box-shadow:0 12px 32px rgba(15,23,42,.06); }}
.audit .label {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
.audit strong {{ display:block; margin-top:4px; font-size:18px; }}
.ok {{ color:#047857; }} .bad {{ color:#b42318; }}
.grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-bottom:22px; }}
.card {{ background:rgba(255,255,255,.86); backdrop-filter:blur(12px); border:1px solid rgba(226,232,240,.9); border-radius:18px; padding:18px; box-shadow:0 12px 32px rgba(15,23,42,.05); }}
.card .label {{ color:var(--muted); font-size:13px; }}
.card .value {{ display:block; margin-top:8px; font-size:28px; font-weight:750; letter-spacing:-.04em; }}
.panel {{ background:var(--surface); border:1px solid var(--line); border-radius:22px; overflow:hidden; box-shadow:0 20px 45px rgba(15,23,42,.07); }}
.panel-head {{ padding:20px 22px; display:flex; justify-content:space-between; gap:16px; align-items:end; border-bottom:1px solid var(--line); }}
.panel-head h2 {{ margin:0; font-size:18px; }}
.panel-head p {{ margin:4px 0 0; color:var(--muted); font-size:13px; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ padding:15px 18px; text-align:left; border-bottom:1px solid var(--line); font-size:14px; }}
th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.08em; background:var(--soft); }}
tr:last-child td {{ border-bottom:0; }}
.status {{ display:inline-flex; align-items:center; padding:5px 9px; border-radius:999px; background:#eef2f7; font-size:12px; font-weight:700; }}
.status-pending_human_approval {{ background:#fff7ed; color:#c2410c; }}
.status-approved,.status-auto_approved {{ background:#ecfdf5; color:#047857; }}
.status-rejected {{ background:#fef2f2; color:#b42318; }}
.empty {{ text-align:center; color:var(--muted); padding:42px; }}
code {{ font-size:12px; }}
@media (max-width: 900px) {{ .grid {{ grid-template-columns:repeat(2,1fr); }} .topbar {{ flex-direction:column; }} .audit {{ width:100%; }} }}
@media (max-width: 620px) {{ .shell {{ padding:28px 14px; }} .grid {{ grid-template-columns:1fr 1fr; }} th,td {{ padding:12px 10px; }} .hide-mobile {{ display:none; }} }}
</style>
</head>
<body>
<div class="shell">
  <div class="topbar">
    <div class="brand">
      <div class="eyebrow">ApexOperator • Finance Operations</div>
      <h1>Operations Control Room</h1>
      <p class="subtitle">Bounded agent execution, deterministic policy enforcement, human approval, and cryptographic auditability in one view.</p>
    </div>
    <div class="audit">
      <div class="label">Audit integrity</div>
      <strong class="{audit_class}">● {audit_label}</strong>
    </div>
  </div>

  <div class="grid">
    <div class="card"><span class="label">Pending approval</span><span class="value">{pending}</span></div>
    <div class="card"><span class="label">Auto approved</span><span class="value">{auto_approved}</span></div>
    <div class="card"><span class="label">Approved</span><span class="value">{approved}</span></div>
    <div class="card"><span class="label">Rejected</span><span class="value">{rejected}</span></div>
  </div>

  <section class="panel">
    <div class="panel-head">
      <div>
        <h2>Recent operations</h2>
        <p>Latest persisted tasks visible to the finance operations role.</p>
      </div>
      <div class="eyebrow">{len(tasks)} records</div>
    </div>
    <table>
      <thead>
        <tr><th>Task</th><th>Invoice</th><th>Status</th><th>Requested by</th><th class="hide-mobile">Reviewer</th></tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </section>
</div>
</body>
</html>"""
        return HTMLResponse(html)

    return api
