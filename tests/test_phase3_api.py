import json

import pymupdf

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



def invoice_pdf(*, invoice_id="OWN-001", vendor="My Vendor", subtotal="4000.00", tax="400.00", total="4400.00"):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                f"Invoice ID: {invoice_id}",
                f"Vendor: {vendor}",
                f"Subtotal: {subtotal}",
                f"Tax: {tax}",
                f"Total: {total}",
            ]
        ),
    )
    content = document.tobytes()
    document.close()
    return content


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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


def test_duplicate_invoice_submission_is_idempotent(tmp_path):
    client = make_client(tmp_path)
    payload = {"invoice_id": "INV-LOW-001", "justification": "First submission"}

    first = client.post("/tasks", json=payload, headers=auth("clerk-token"))
    second = client.post(
        "/tasks",
        json={"invoice_id": "INV-LOW-001", "justification": "Duplicate submission"},
        headers=auth("clerk-token"),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["task_id"] == first.json()["task_id"]
    assert second.json()["status"] == "AUTO_APPROVED"


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


def test_ready_and_secured_dashboard(tmp_path):
    client = make_client(tmp_path)
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}

    denied = client.get("/dashboard", headers=auth("clerk-token"))
    allowed = client.get("/dashboard", headers=auth("manager-token"))

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert "Operations Control Room" in allowed.text
    assert "Pending approval" in allowed.text




def test_uploaded_invoice_pdf_is_extracted_and_governed(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/documents/invoices/process",
        files={"document": ("my-invoice.pdf", invoice_pdf(), "application/pdf")},
        data={"justification": "Process my own invoice"},
        headers=auth("clerk-token"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["document"]["invoice_id"] == "OWN-001"
    assert body["document"]["vendor_name"] == "My Vendor"
    assert body["document"]["total"] == "4400.00"
    assert body["task"]["status"] == "AUTO_APPROVED"
    assert body["task"]["invoice_id"] == "OWN-001"


def test_uploaded_invoice_pdf_above_threshold_requires_human(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/documents/invoices/process",
        files={"document": ("high.pdf", invoice_pdf(subtotal="6000.00", tax="600.00", total="6600.00"), "application/pdf")},
        headers=auth("clerk-token"),
    )

    assert response.status_code == 200
    assert response.json()["task"]["status"] == "PENDING_HUMAN_APPROVAL"


def test_uploaded_invoice_math_mismatch_is_rejected_by_policy(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/documents/invoices/process",
        files={"document": ("bad.pdf", invoice_pdf(subtotal="6000.00", tax="600.00", total="7000.00"), "application/pdf")},
        headers=auth("clerk-token"),
    )

    assert response.status_code == 200
    assert response.json()["task"]["status"] == "REJECTED"


def test_uploaded_document_requires_pdf(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/documents/invoices/process",
        files={"document": ("invoice.txt", b"not a pdf", "text/plain")},
        headers=auth("clerk-token"),
    )
    assert response.status_code == 415
