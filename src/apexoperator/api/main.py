from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

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

    api = FastAPI(title="ApexOperator API", version="0.2.0")
    api.state.authenticator = authenticator
    api.state.service = service
    api.state.engine = engine

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

        tasks = request.app.state.service.task_store.list_recent(50)
        audit_ok = request.app.state.service.audit_ledger.verify_integrity()

        rows = "".join(
            f"<tr><td>{t['task_id']}</td><td>{t['invoice_id']}</td>"
            f"<td>{t['status']}</td><td>{t['requested_by']}</td>"
            f"<td>{t['reviewer'] or ''}</td></tr>"
            for t in tasks
        )
        html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>ApexOperator Dashboard</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ddd;padding:.5rem;text-align:left}}
.bad{{color:#b42318}} .ok{{color:#067647}}
</style></head>
<body>
<h1>ApexOperator Operations Dashboard</h1>
<p>Audit integrity:
<strong class="{'ok' if audit_ok else 'bad'}">{'VALID' if audit_ok else 'INVALID'}</strong></p>
<table><thead><tr><th>Task</th><th>Invoice</th><th>Status</th><th>Requested By</th><th>Reviewer</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>"""
        return HTMLResponse(html)

    return api
