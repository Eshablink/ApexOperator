import hmac
import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from apexoperator.agent.openai_planner import OpenAIPlanner
from apexoperator.agent.runtime import MockPlanner
from apexoperator.config import settings
from apexoperator.observability.logging import configure_logging, log_request

from apexoperator.api.schemas import (
    ApprovalRequest,
    LoginRequest,
    AuditVerificationResponse,
    CreateTaskRequest,
    TaskResponse,
    DocumentProcessResponse,
    CreateUserRequest,
    UserResponse,
)
from apexoperator.persistence.database import init_database, make_engine, make_session_factory
from apexoperator.documents.extract import ExtractionError, InvoiceDocumentExtractor
from apexoperator.documents.security import DocumentSecurityError
from apexoperator.domain.invoice import Invoice
from apexoperator.persistence.sqlalchemy_audit import SQLAlchemyAuditLedger
from apexoperator.persistence.sqlalchemy_tasks import SQLAlchemyTaskStore
from apexoperator.persistence.models import UserRecord
from apexoperator.security.auth import hash_password
from apexoperator.security.auth import InMemoryAuthenticator, JWTAuthenticator, Principal, ensure_bootstrap_user
from apexoperator.security.rbac import Permission, RBAC, Role
from apexoperator.service.approvals import ApprovalService


def create_app(
    *,
    workspace_dir: str | Path = "workspace",
    database_path: str | Path | None = None,
    database_url: str | None = None,
    authenticator: InMemoryAuthenticator | JWTAuthenticator | None = None,
    planner = None,
) -> FastAPI:
    resolved_url = database_url or (settings.database_url if database_path is None else f"sqlite:///{Path(database_path).resolve()}")
    engine = make_engine(resolved_url)
    init_database(engine)
    sessions = make_session_factory(engine)

    if authenticator is None:
        if settings.app_env == "production":
            if not settings.jwt_secret or not settings.bootstrap_email or not settings.bootstrap_password_hash:
                raise RuntimeError("production authentication is not configured")
            ensure_bootstrap_user(
                sessions,
                email=settings.bootstrap_email,
                password_hash=settings.bootstrap_password_hash,
                role=Role(settings.bootstrap_role),
                organization_id=settings.organization_id,
            )
            authenticator = JWTAuthenticator(
                session_factory=sessions,
                secret=settings.jwt_secret,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                session_minutes=settings.session_minutes,
                cookie_secure=True,
            )
        else:
            authenticator = InMemoryAuthenticator(
                {
                    "dev-clerk-token": Principal("dev-clerk", Role.AP_CLERK, "demo"),
                    "dev-manager-token": Principal("dev-manager", Role.FINANCE_MANAGER, "demo"),
                    "dev-admin-token": Principal("dev-admin", Role.SYSTEM_ADMIN, "demo"),
                }
            )
    task_store = SQLAlchemyTaskStore(sessions)
    audit_ledger = SQLAlchemyAuditLedger(sessions)

    resolved_planner = planner
    if resolved_planner is None:
        if settings.planner_mode == "openai":
            if not settings.openai_api_key:
                raise RuntimeError("APEX_PLANNER=openai requires OPENAI_API_KEY")
            resolved_planner = OpenAIPlanner(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
            )
        else:
            resolved_planner = MockPlanner()

    service = ApprovalService(
        workspace_dir=str(workspace_dir),
        task_store=task_store,
        audit_ledger=audit_ledger,
        planner=resolved_planner,
    )

    logger = configure_logging()
    api = FastAPI(title="ApexOperator API", version="0.3.0")
    api.state.authenticator = authenticator
    api.state.service = service
    api.state.engine = engine

    # When the package is installed into site-packages (as it is in the
    # production Docker image), __file__ no longer lives under the repository
    # root. Prefer the container's copied frontend directory, while retaining
    # the repository-relative path for local/editable installs.
    frontend_candidates = [
        Path(os.getenv("APEX_FRONTEND_DIR", "/app/frontend")),
        Path(__file__).resolve().parents[3] / "frontend",
    ]
    frontend_dir = next(
        (
            path
            for path in frontend_candidates
            if (path / "index.html").is_file() and (path / "assets").is_dir()
        ),
        None,
    )
    if frontend_dir is None:
        raise RuntimeError(
            "Frontend assets are missing; expected /app/frontend or a repository frontend directory"
        )

    frontend_assets = frontend_dir / "assets"
    api.mount(
        "/assets",
        StaticFiles(directory=str(frontend_assets)),
        name="frontend-assets",
    )

    @api.get("/", include_in_schema=False)
    def frontend_home() -> FileResponse:
        return FileResponse(frontend_dir / "index.html")

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

    def _session_token(request: Request) -> str | None:
        cookie_token = request.cookies.get(JWTAuthenticator.SESSION_COOKIE)
        if cookie_token:
            return cookie_token
        authorization = request.headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            token = authorization.removeprefix("Bearer ").strip()
            if token:
                return token
        return None

    def _require_csrf(request: Request) -> None:
        if settings.app_env != "production" or request.method in {"GET", "HEAD", "OPTIONS"}:
            return
        expected = request.cookies.get(JWTAuthenticator.CSRF_COOKIE)
        supplied = request.headers.get("X-CSRF-Token")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            raise HTTPException(status_code=403, detail="csrf validation failed")

    def principal(request: Request) -> Principal:
        token = _session_token(request)
        if not token:
            raise HTTPException(status_code=401, detail="authentication required", headers={"WWW-Authenticate": "Bearer"})
        _require_csrf(request)
        return request.app.state.authenticator.authenticate(token)

    @api.get("/auth/config")
    def auth_config() -> dict[str, Any]:
        return {
            "mode": settings.app_env,
            "production": settings.app_env == "production",
            "roles": [role.value for role in Role],
            "session_minutes": settings.session_minutes if settings.app_env == "production" else None,
        }

    @api.get("/auth/me")
    def auth_me(request: Request) -> dict[str, str]:
        current = principal(request)
        return {"actor_id": current.actor_id, "role": current.role.value, "organization_id": current.organization_id}

    @api.post("/auth/login")
    def auth_login(body: LoginRequest, request: Request, response: Response) -> dict[str, str]:
        if settings.app_env != "production":
            raise HTTPException(status_code=404, detail="production authentication is disabled")
        token, current, csrf_token, max_age = request.app.state.authenticator.login(body.email, body.password)
        response.set_cookie(key=JWTAuthenticator.SESSION_COOKIE, value=token, max_age=max_age, httponly=True, secure=True, samesite="lax", path="/")
        response.set_cookie(key=JWTAuthenticator.CSRF_COOKIE, value=csrf_token, max_age=max_age, httponly=False, secure=True, samesite="lax", path="/")
        return {"actor_id": current.actor_id, "role": current.role.value}

    @api.post("/admin/users", response_model=UserResponse)
    def create_user(body: CreateUserRequest, request: Request) -> UserResponse:
        current = principal(request)
        if current.role != Role.SYSTEM_ADMIN:
            raise HTTPException(status_code=403, detail="system administrator permission required")
        with sessions.begin() as session:
            if session.scalar(select(UserRecord).where(UserRecord.email == body.email)) is not None:
                raise HTTPException(status_code=409, detail="email already registered")
            user = UserRecord(
                actor_id=f"user-{secrets.token_hex(8)}",
                email=body.email,
                organization_id=current.organization_id,
                role=body.role,
                password_hash=hash_password(body.password),
                is_active=True,
            )
            session.add(user)
            session.flush()
            return UserResponse(actor_id=user.actor_id, email=user.email, role=user.role, organization_id=user.organization_id, is_active=user.is_active)

    @api.post("/auth/logout")
    def auth_logout(request: Request, response: Response) -> dict[str, str]:
        if settings.app_env == "production":
            _require_csrf(request)
        token = _session_token(request)
        if token and settings.app_env == "production":
            request.app.state.authenticator.logout(token)
        response.delete_cookie(JWTAuthenticator.SESSION_COOKIE, path="/")
        response.delete_cookie(JWTAuthenticator.CSRF_COOKIE, path="/")
        return {"status": "signed_out"}

    @api.api_route("/health", methods=["GET", "HEAD"])
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

    @api.post("/documents/invoices/process", response_model=DocumentProcessResponse)
    async def process_invoice_document(
        request: Request,
        document: UploadFile = File(...),
        justification: str | None = Query(default=None, max_length=4000),
    ) -> DocumentProcessResponse:
        current = principal(request)
        filename = (document.filename or "").strip()
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=415, detail="only PDF invoice documents are supported")
        if document.content_type not in {None, "", "application/pdf", "application/octet-stream"}:
            raise HTTPException(status_code=415, detail="unsupported document content type")

        content = await document.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="document exceeds the 10 MB upload limit")
        try:
            extraction = InvoiceDocumentExtractor().extract_pdf(content)
        except (DocumentSecurityError, ExtractionError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        task = request.app.state.service.create_task_from_document(
            Invoice(
                invoice_id=extraction.invoice_id,
                vendor_name=extraction.vendor_name,
                subtotal=extraction.subtotal,
                tax=extraction.tax,
                total=extraction.total,
            ),
            current,
            justification=(justification or "").strip() or None,
            confidence=extraction.confidence_class.value,
        )
        return DocumentProcessResponse(
            task=task,
            document={
                "filename": filename,
                "invoice_id": extraction.invoice_id,
                "vendor_name": extraction.vendor_name,
                "subtotal": str(extraction.subtotal),
                "tax": str(extraction.tax),
                "total": str(extraction.total),
                "confidence": str(extraction.confidence),
                "confidence_class": extraction.confidence_class.value,
            },
        )
    @api.get("/tasks/{task_id}", response_model=TaskResponse)
    def get_task(task_id: str, request: Request) -> TaskResponse:
        return request.app.state.service.get_task(task_id, principal(request))

    @api.post("/tasks/{task_id}/approve", response_model=TaskResponse)
    def approve_task(task_id: str, body: ApprovalRequest, request: Request) -> TaskResponse:
        return request.app.state.service.review_task(task_id, body, principal(request), approve=True)

    @api.post("/tasks/{task_id}/reject", response_model=TaskResponse)
    def reject_task(task_id: str, body: ApprovalRequest, request: Request) -> TaskResponse:
        return request.app.state.service.review_task(task_id, body, principal(request), approve=False)

    @api.get("/audit/verify", response_model=AuditVerificationResponse)
    def verify_audit(request: Request) -> dict[str, bool]:
        return request.app.state.service.verify_audit(principal(request))

    @api.get("/dashboard/data")
    def dashboard_data(request: Request) -> dict:
        reviewer = principal(request)
        if not RBAC.is_allowed(reviewer.role, Permission.AUDIT_READ):
            raise HTTPException(status_code=403, detail="permission denied")

        tasks = request.app.state.service.list_tasks(reviewer, 50)
        counts: dict[str, int] = {}
        for task in tasks:
            status = str(task["status"])
            counts[status] = counts.get(status, 0) + 1

        return {
            "audit_ok": request.app.state.service.audit_ledger.verify_integrity(),
            "counts": counts,
            "tasks": tasks,
            "planner": {
                "mode": settings.planner_mode,
                "model": settings.openai_model if settings.planner_mode == "openai" else None,
                "max_steps": request.app.state.service.runtime.MAX_STEPS,
                "max_retries": request.app.state.service.runtime.MAX_RETRIES,
            },
        }

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
