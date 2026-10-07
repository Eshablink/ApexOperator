import csv
import hmac
import io
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

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
)
from apexoperator.persistence.database import init_database, make_engine, make_session_factory
from apexoperator.persistence.sqlalchemy_audit import SQLAlchemyAuditLedger
from apexoperator.persistence.sqlalchemy_tasks import SQLAlchemyTaskStore
from apexoperator.security.auth import InMemoryAuthenticator, JWTAuthenticator, Principal, ensure_bootstrap_user
from apexoperator.security.rbac import Permission, RBAC, Role
from apexoperator.service.approvals import ApprovalService


_LOGIN_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_FAILURE_LIMIT = 5


def _prune_login_attempts(key: str, now: float) -> deque[float]:
    attempts = _LOGIN_ATTEMPTS[key]
    while attempts and now - attempts[0] > _LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    return attempts


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
                    "dev-clerk-token": Principal("dev-clerk", Role.AP_CLERK),
                    "dev-manager-token": Principal("dev-manager", Role.FINANCE_MANAGER),
                    "dev-admin-token": Principal("dev-admin", Role.SYSTEM_ADMIN),
                }
            )

    task_store = SQLAlchemyTaskStore(sessions)
    audit_ledger = SQLAlchemyAuditLedger(sessions)

    mock_planner = MockPlanner()
    openai_planner = None
    if settings.openai_api_key:
        openai_planner = OpenAIPlanner(api_key=settings.openai_api_key, model=settings.openai_model)

    resolved_planner = planner
    if resolved_planner is None:
        if settings.planner_mode == "openai":
            if openai_planner is None:
                raise RuntimeError("APEX_PLANNER=openai requires OPENAI_API_KEY")
            resolved_planner = openai_planner
        elif settings.planner_mode == "auto" and openai_planner is not None:
            resolved_planner = openai_planner
        else:
            resolved_planner = mock_planner

    planners: dict[str, Any] = {
        "auto": resolved_planner,
        "mock": mock_planner if planner is None else planner,
    }
    if openai_planner is not None:
        planners["openai"] = openai_planner

    service = ApprovalService(
        workspace_dir=str(workspace_dir),
        task_store=task_store,
        audit_ledger=audit_ledger,
        planner=resolved_planner,
        planners=planners,
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
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        if settings.app_env == "production" and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
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
        live_available = "openai" in service.planners
        active_mode = settings.planner_mode
        if active_mode == "auto":
            active_mode = "openai" if live_available else "mock"
        return {
            "mode": settings.app_env,
            "production": settings.app_env == "production",
            "roles": [role.value for role in Role],
            "session_minutes": settings.session_minutes if settings.app_env == "production" else None,
            "planner": {
                "selection": settings.planner_mode,
                "active": active_mode,
                "live_available": live_available,
                "model": settings.openai_model if live_available else None,
            },
        }

    @api.get("/auth/me")
    def auth_me(request: Request) -> dict[str, str]:
        current = principal(request)
        return {"actor_id": current.actor_id, "role": current.role.value}

    @api.post("/auth/login")
    def auth_login(body: LoginRequest, request: Request, response: Response) -> dict[str, str]:
        if settings.app_env != "production":
            raise HTTPException(status_code=404, detail="production authentication is disabled")
        key = f"{request.client.host if request.client else 'unknown'}:{body.email}"
        now = time.monotonic()
        attempts = _prune_login_attempts(key, now)
        if len(attempts) >= _LOGIN_FAILURE_LIMIT:
            retry_after = max(1, int(_LOGIN_WINDOW_SECONDS - (now - attempts[0])))
            raise HTTPException(status_code=429, detail="too many failed login attempts; retry later", headers={"Retry-After": str(retry_after)})
        try:
            token, current, csrf_token, max_age = request.app.state.authenticator.login(body.email, body.password)
        except Exception:
            attempts.append(now)
            raise
        attempts.clear()
        response.set_cookie(key=JWTAuthenticator.SESSION_COOKIE, value=token, max_age=max_age, httponly=True, secure=True, samesite="lax", path="/")
        response.set_cookie(key=JWTAuthenticator.CSRF_COOKIE, value=csrf_token, max_age=max_age, httponly=False, secure=True, samesite="lax", path="/")
        return {"actor_id": current.actor_id, "role": current.role.value}

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
    def create_task(body: CreateTaskRequest, request: Request, planner: Literal["auto", "mock", "openai"] = Query(default="auto")) -> TaskResponse:
        return request.app.state.service.create_task(body, principal(request), planner)

    @api.get("/tasks/{task_id}", response_model=TaskResponse)
    def get_task(task_id: str, request: Request) -> TaskResponse:
        return request.app.state.service.get_task(task_id)

    @api.get("/tasks/{task_id}/detail")
    def task_detail(task_id: str, request: Request) -> dict[str, Any]:
        reviewer = principal(request)
        if not RBAC.is_allowed(reviewer.role, Permission.AUDIT_READ):
            raise HTTPException(status_code=403, detail="permission denied")
        return request.app.state.service.task_detail(task_id)

    @api.post("/tasks/{task_id}/approve", response_model=TaskResponse)
    def approve_task(task_id: str, body: ApprovalRequest, request: Request) -> TaskResponse:
        return request.app.state.service.review_task(task_id, body, principal(request), approve=True)

    @api.post("/tasks/{task_id}/reject", response_model=TaskResponse)
    def reject_task(task_id: str, body: ApprovalRequest, request: Request) -> TaskResponse:
        return request.app.state.service.review_task(task_id, body, principal(request), approve=False)

    @api.get("/audit/verify", response_model=AuditVerificationResponse)
    def verify_audit(request: Request) -> dict[str, bool]:
        return request.app.state.service.verify_audit(principal(request))

    @api.post("/audit/tamper-demo")
    def tamper_demo(request: Request) -> dict[str, Any]:
        reviewer = principal(request)
        if not RBAC.is_allowed(reviewer.role, Permission.AUDIT_VERIFY):
            raise HTTPException(status_code=403, detail="permission denied")
        if settings.app_env == "production":
            raise HTTPException(status_code=403, detail="tamper demo is disabled in production")
        return request.app.state.service.audit_ledger.simulate_tamper()

    @api.get("/audit/export")
    def audit_export(request: Request, format: Literal["json", "csv"] = Query(default="json")) -> Response:
        import json
        reviewer = principal(request)
        if not RBAC.is_allowed(reviewer.role, Permission.AUDIT_READ):
            raise HTTPException(status_code=403, detail="permission denied")
        events = request.app.state.service.audit_ledger.list_events(limit=1000)
        if format == "json":
            return Response(content=json.dumps(events, ensure_ascii=False, indent=2), media_type="application/json", headers={"Content-Disposition": "attachment; filename=apexoperator-audit.json"})
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["sequence_id","timestamp","event_type","event_id","action","event_hash","previous_hash","after_state"])
        for event in events:
            writer.writerow([event["sequence_id"],event["timestamp"],event["event_type"],event["event_id"],event["action"],event["event_hash"],event["previous_hash"],json.dumps(event["after_state"], ensure_ascii=False, sort_keys=True)])
        return Response(content=stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=apexoperator-audit.csv"})

    @api.post("/demo/reset")
    def reset_demo(request: Request) -> dict[str, str]:
        reviewer = principal(request)
        if settings.app_env == "production":
            raise HTTPException(status_code=403, detail="demo reset is disabled in production")
        if not RBAC.is_allowed(reviewer.role, Permission.AUDIT_VERIFY):
            raise HTTPException(status_code=403, detail="permission denied")
        request.app.state.service.task_store.reset_demo()
        request.app.state.service.audit_ledger.reset_demo()
        return {"status": "reset", "message": "demo data and audit chain reset"}

    @api.get("/dashboard/data")
    def dashboard_data(request: Request) -> dict:
        reviewer = principal(request)
        if not RBAC.is_allowed(reviewer.role, Permission.AUDIT_READ):
            raise HTTPException(status_code=403, detail="permission denied")

        tasks = request.app.state.service.task_store.list_recent(50)
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
                "active": "openai" if settings.planner_mode == "auto" and "openai" in service.planners else settings.planner_mode,
                "live_available": "openai" in service.planners,
                "model": settings.openai_model if "openai" in service.planners else None,
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
