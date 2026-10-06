from pathlib import Path

from fastapi import FastAPI, Request

from apexoperator.api.schemas import ApprovalRequest, AuditVerificationResponse, CreateTaskRequest, TaskResponse
from apexoperator.persistence.tasks import TaskStore
from apexoperator.security.auth import InMemoryAuthenticator, Principal
from apexoperator.security.rbac import Role
from apexoperator.service.approvals import ApprovalService


def create_app(
    *,
    workspace_dir: str | Path = "workspace",
    database_path: str | Path = "apexoperator_api.sqlite3",
    authenticator: InMemoryAuthenticator | None = None,
) -> FastAPI:
    authenticator = authenticator or InMemoryAuthenticator(
        {
            "dev-clerk-token": Principal("dev-clerk", Role.AP_CLERK),
            "dev-manager-token": Principal("dev-manager", Role.FINANCE_MANAGER),
            "dev-admin-token": Principal("dev-admin", Role.SYSTEM_ADMIN),
        }
    )
    task_store = TaskStore(database_path)
    from apexoperator.audit.ledger import CryptographicAuditLedger

    service = ApprovalService(
        workspace_dir=str(workspace_dir),
        task_store=task_store,
        audit_ledger=CryptographicAuditLedger(),
    )

    api = FastAPI(title="ApexOperator API", version="0.1.0")
    api.state.authenticator = authenticator
    api.state.service = service

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    def principal(request: Request) -> Principal:
        import base64
        from fastapi import HTTPException

        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="authorization required")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(status_code=401, detail="authorization required")
        return request.app.state.authenticator.authenticate(token)

    @api.post("/tasks", response_model=TaskResponse)
    def create_task(body: CreateTaskRequest, request: Request) -> TaskResponse:
        return request.app.state.service.create_task(body, principal(request))

    @api.get("/tasks/{task_id}", response_model=TaskResponse)
    def get_task(task_id: str, request: Request) -> TaskResponse:
        return request.app.state.service.get_task(task_id)

    @api.post("/tasks/{task_id}/approve", response_model=TaskResponse)
    def approve_task(task_id: str, body: ApprovalRequest, request: Request) -> TaskResponse:
        return request.app.state.service.review_task(
            task_id, body, principal(request), approve=True
        )

    @api.post("/tasks/{task_id}/reject", response_model=TaskResponse)
    def reject_task(task_id: str, body: ApprovalRequest, request: Request) -> TaskResponse:
        return request.app.state.service.review_task(
            task_id, body, principal(request), approve=False
        )

    @api.get("/audit/verify", response_model=AuditVerificationResponse)
    def verify_audit(request: Request) -> dict[str, bool]:
        return request.app.state.service.verify_audit(principal(request))

    return api
