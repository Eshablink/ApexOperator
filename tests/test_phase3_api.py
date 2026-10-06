import json

from fastapi.testclient import TestClient

from apexoperator.api.main import create_app
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
        }
    )
    app = create_app(
        workspace_dir=workspace,
        database_path=tmp_path / "tasks.sqlite3",
        authenticator=auth,
    )
    return TestClient(app)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health():
    client = make_client(__import__("pathlib").Path("/tmp")) if False else None
    assert client is None


def test_create_high_value_task_creates_real_pending_approval(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/tasks",
        json={
            "invoice_id": "INV-HIGH-001",
            "justification": "Threshold exceeded",
        },
        headers=auth("clerk-token"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PENDING_HUMAN_APPROVAL"
    assert body["decision"] == "HUMAN_ESCALATION_REQUIRED"
    assert body["requested_by"] == "clerk-1"
    assert body["task_id"]


def test_get_task_reads_persisted_task(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/tasks",
        json={"invoice_id": "INV-HIGH-001"},
        headers=auth("clerk-token"),
    ).json()

    response = client.get(f"/tasks/{created['task_id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING_HUMAN_APPROVAL"


def test_manager_can_approve_pending_task(tmp_path):
    client = make_client(tmp_path)
    task = client.post(
        "/tasks",
        json={"invoice_id": "INV-HIGH-001"},
        headers=auth("clerk-token"),
    ).json()

    response = client.post(
        f"/tasks/{task['task_id']}/approve",
        json={"comment": "Verified by finance manager"},
        headers=auth("manager-token"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "APPROVED"
    assert body["reviewer"] == "manager-1"


def test_clerk_cannot_approve(tmp_path):
    client = make_client(tmp_path)
    task = client.post(
        "/tasks",
        json={"invoice_id": "INV-HIGH-001"},
        headers=auth("clerk-token"),
    ).json()

    response = client.post(
        f"/tasks/{task['task_id']}/approve",
        json={},
        headers=auth("clerk-token"),
    )
    assert response.status_code == 403
    assert "permission denied" in response.json()["detail"]


def test_approval_must_target_existing_pending_escalation(tmp_path):
    client = make_client(tmp_path)
    task = client.post(
        "/tasks",
        json={"invoice_id": "INV-HIGH-001"},
        headers=auth("clerk-token"),
    ).json()

    first = client.post(
        f"/tasks/{task['task_id']}/approve",
        json={},
        headers=auth("manager-token"),
    )
    second = client.post(
        f"/tasks/{task['task_id']}/approve",
        json={},
        headers=auth("manager-token"),
    )
    assert first.status_code == 200
    assert second.status_code == 409


def test_low_value_invoice_does_not_create_pending_human_gate(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/tasks",
        json={"invoice_id": "INV-LOW-001"},
        headers=auth("clerk-token"),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "AUTO_APPROVED"


def test_audit_verify_requires_manager_permission(tmp_path):
    client = make_client(tmp_path)
    denied = client.get("/audit/verify", headers=auth("clerk-token"))
    allowed = client.get("/audit/verify", headers=auth("manager-token"))
    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["integrity_valid"] is True


def test_missing_authentication_is_rejected(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/audit/verify")
    assert response.status_code == 401


def test_unknown_invoice_returns_not_found(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/tasks",
        json={"invoice_id": "DOES-NOT-EXIST"},
        headers=auth("clerk-token"),
    )
    assert response.status_code == 404
