import json

from fastapi.testclient import TestClient

from apexoperator.api.main import create_app
from apexoperator.persistence.models import Base
from apexoperator.security.auth import InMemoryAuthenticator, Principal
from apexoperator.security.rbac import Role


def make_client(tmp_path):
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
    auth = InMemoryAuthenticator(
        {
            "clerk-token": Principal("clerk-1", Role.AP_CLERK),
            "manager-token": Principal("manager-1", Role.FINANCE_MANAGER),
            "admin-token": Principal("admin-1", Role.SYSTEM_ADMIN),
        }
    )
    app = create_app(
        workspace_dir=workspace,
        database_path=tmp_path / "tasks.sqlite3",
        authenticator=auth,
    )
    return TestClient(app)


def auth(token):
    return {"Authorization": "Bearer " + token}


def test_security_headers_are_present(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_task_detail_contains_planner_proposals_and_audit_timeline(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/tasks",
        json={
            "invoice_id": "INV-HIGH-001",
            "justification": "Threshold review",
            "planner_mode": "mock",
        },
        headers=auth("clerk-token"),
    )
    assert created.status_code == 200
    task_id = created.json()["task_id"]

    detail = client.get("/tasks/" + task_id + "/detail")
    assert detail.status_code == 200
    body = detail.json()
    assert body["policy_decision"] == "HUMAN_ESCALATION_REQUIRED"
    assert body["planner_proposals"]
    assert body["audit_timeline"]


def test_review_requires_reason_and_is_idempotent_under_repeat_review(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/tasks",
        json={"invoice_id": "INV-HIGH-001", "justification": "Review"},
        headers=auth("clerk-token"),
    )
    task_id = created.json()["task_id"]

    missing_reason = client.post(
        "/tasks/" + task_id + "/approve",
        json={},
        headers=auth("manager-token"),
    )
    assert missing_reason.status_code == 422

    approved = client.post(
        "/tasks/" + task_id + "/approve",
        json={"comment": "Verified supplier and threshold context."},
        headers=auth("manager-token"),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    repeated = client.post(
        "/tasks/" + task_id + "/approve",
        json={"comment": "Duplicate review attempt."},
        headers=auth("manager-token"),
    )
    assert repeated.status_code == 409
    assert "already decided" in repeated.json()["detail"]


def test_tamper_demo_breaks_integrity_and_export_works(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/tasks",
        json={"invoice_id": "INV-LOW-001", "justification": "Routine processing"},
        headers=auth("clerk-token"),
    )
    assert created.status_code == 200

    tampered = client.post("/audit/tamper-demo", headers=auth("admin-token"))
    assert tampered.status_code == 200
    assert tampered.json()["integrity_valid"] is False

    verify = client.get("/audit/verify", headers=auth("admin-token"))
    assert verify.status_code == 200
    assert verify.json()["integrity_valid"] is False

    exported = client.get("/audit/export?format=json", headers=auth("admin-token"))
    assert exported.status_code == 200
    assert exported.headers["Content-Disposition"].endswith("apexoperator-audit.json")
    assert "TOOL_EXECUTED" in exported.text


def test_demo_reset_clears_tasks_and_restores_audit_integrity(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/tasks",
        json={"invoice_id": "INV-LOW-001", "justification": "Routine processing"},
        headers=auth("clerk-token"),
    )
    assert created.status_code == 200

    reset = client.post("/demo/reset", headers=auth("admin-token"))
    assert reset.status_code == 200

    data = client.get("/dashboard/data?page=1&page_size=5", headers=auth("manager-token"))
    assert data.status_code == 200
    assert data.json()["total"] == 0
    assert data.json()["audit_ok"] is True

    Base.metadata.drop_all(client.app.state.engine)
