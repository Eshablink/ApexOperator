import json

from fastapi.testclient import TestClient

from apexoperator.api.main import create_app
from apexoperator.security.auth import InMemoryAuthenticator, Principal
from apexoperator.security.rate_limit import LoginRateLimiter
from apexoperator.security.rbac import Role


def make_client(tmp_path, *, include_admin=True):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "incoming_batch.json").write_text(
        json.dumps(
            {
                "invoices": [
                    {
                        "invoice_id": "INV-HIGH-001",
                        "vendor_name": "Enterprise Systems",
                        "subtotal": "6000.00",
                        "tax": "600.00",
                        "total": "6600.00",
                    },
                    {
                        "invoice_id": "INV-LOW-001",
                        "vendor_name": "Acme Supplies",
                        "subtotal": "1000.00",
                        "tax": "100.00",
                        "total": "1100.00",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    tokens = {
        "clerk-token": Principal("clerk-1", Role.AP_CLERK),
        "manager-token": Principal("manager-1", Role.FINANCE_MANAGER),
    }
    if include_admin:
        tokens["admin-token"] = Principal("admin-1", Role.SYSTEM_ADMIN)
    auth = InMemoryAuthenticator(tokens)
    return TestClient(
        create_app(
            workspace_dir=workspace,
            database_path=tmp_path / "tasks.sqlite3",
            authenticator=auth,
        )
    )


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_task_detail_contains_planner_policy_and_task_audit(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/tasks",
        json={
            "invoice_id": "INV-HIGH-001",
            "justification": "Threshold review",
            "planner_mode": "openai",
        },
        headers=auth("clerk-token"),
    )
    assert created.status_code == 200
    task_id = created.json()["task_id"]

    detail = client.get(
        f"/tasks/{task_id}/detail",
        headers=auth("manager-token"),
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["task"]["invoice_id"] == "INV-HIGH-001"
    assert body["planner"]["planner_mode"] in {"mock", "openai"}
    assert body["planner"]["policy_decision"]["decision"] == "HUMAN_ESCALATION_REQUIRED"
    assert any(event["event_type"] == "PLANNER_PROPOSAL" for event in body["audit_timeline"])
    assert any(event["event_type"] == "TASK_CREATED" for event in body["audit_timeline"])


def test_approval_reason_is_required_and_second_decision_is_conflict(tmp_path):
    client = make_client(tmp_path)
    task = client.post(
        "/tasks",
        json={"invoice_id": "INV-HIGH-001"},
        headers=auth("clerk-token"),
    ).json()
    missing = client.post(
        f"/tasks/{task['task_id']}/approve",
        json={},
        headers=auth("manager-token"),
    )
    assert missing.status_code == 422

    approved = client.post(
        f"/tasks/{task['task_id']}/approve",
        json={"comment": "Verified source invoice and deterministic threshold."},
        headers=auth("manager-token"),
    )
    assert approved.status_code == 200

    duplicate = client.post(
        f"/tasks/{task['task_id']}/approve",
        json={"comment": "Duplicate review should be blocked."},
        headers=auth("manager-token"),
    )
    assert duplicate.status_code == 409
    assert "already decided" in duplicate.json()["detail"]


def test_audit_export_supports_json_and_csv(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/tasks",
        json={"invoice_id": "INV-LOW-001"},
        headers=auth("clerk-token"),
    )
    assert created.status_code == 200

    json_export = client.get("/audit/export?export_format=json", headers=auth("manager-token"))
    assert json_export.status_code == 200
    assert json_export.headers["content-type"].startswith("application/json")
    assert "apexoperator-audit.json" in json_export.headers["content-disposition"]
    assert isinstance(json.loads(json_export.text), list)

    csv_export = client.get("/audit/export?export_format=csv", headers=auth("manager-token"))
    assert csv_export.status_code == 200
    assert csv_export.headers["content-type"].startswith("text/csv")
    assert "apexoperator-audit.csv" in csv_export.headers["content-disposition"]
    assert "event_hash" in csv_export.text


def test_tamper_demo_makes_audit_verification_fail_then_reset_restores_integrity(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/tasks",
        json={"invoice_id": "INV-LOW-001"},
        headers=auth("clerk-token"),
    )
    assert created.status_code == 200

    before = client.get("/audit/verify", headers=auth("manager-token"))
    assert before.json()["integrity_valid"] is True

    tamper = client.post("/audit/demo/tamper", headers=auth("manager-token"))
    assert tamper.status_code == 200
    assert tamper.json()["tampered"] is True

    after = client.get("/audit/verify", headers=auth("manager-token"))
    assert after.status_code == 200
    assert after.json()["integrity_valid"] is False

    reset = client.post("/demo/reset", headers=auth("admin-token"))
    assert reset.status_code == 200
    assert reset.json()["reset"] is True

    restored = client.get("/audit/verify", headers=auth("manager-token"))
    assert restored.json()["integrity_valid"] is True


def test_security_headers_are_present(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


def test_login_rate_limiter_blocks_and_resets():
    limiter = LoginRateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("client:test")[0] is True
    assert limiter.allow("client:test")[0] is True
    allowed, retry_after = limiter.allow("client:test")
    assert allowed is False
    assert retry_after > 0
    limiter.reset("client:test")
    assert limiter.allow("client:test")[0] is True


def test_dashboard_data_supports_server_side_filters_and_pagination(tmp_path):
    client = make_client(tmp_path)
    for invoice_id in ("INV-LOW-001", "INV-HIGH-001", "INV-HIGH-001"):
        response = client.post(
            "/tasks",
            json={"invoice_id": invoice_id},
            headers=auth("clerk-token"),
        )
        assert response.status_code == 200

    pending = client.get(
        "/dashboard/data?limit=1&offset=0&status=PENDING_HUMAN_APPROVAL&q=INV-HIGH",
        headers=auth("manager-token"),
    )
    assert pending.status_code == 200
    body = pending.json()
    assert body["total"] >= 1
    assert len(body["tasks"]) == 1
    assert body["tasks"][0]["status"] == "PENDING_HUMAN_APPROVAL"
    assert "INV-HIGH" in body["tasks"][0]["invoice_id"]
