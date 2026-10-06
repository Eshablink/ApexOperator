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
                        "invoice_id": "INV-LOW-001",
                        "vendor_name": "Acme Supplies",
                        "subtotal": "1000.00",
                        "tax": "100.00",
                        "total": "1100.00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    auth = InMemoryAuthenticator(
        {
            "manager-token": Principal("manager-1", Role.FINANCE_MANAGER),
            "clerk-token": Principal("clerk-1", Role.AP_CLERK),
        }
    )
    return TestClient(
        create_app(
            workspace_dir=workspace,
            database_path=tmp_path / "tasks.sqlite3",
            authenticator=auth,
        )
    )


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_product_home_serves_frontend(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert "ApexOperator" in response.text
    assert "AI that" in response.text


def test_live_dashboard_data_requires_audit_read(tmp_path):
    client = make_client(tmp_path)
    denied = client.get("/dashboard/data", headers=auth("clerk-token"))
    allowed = client.get("/dashboard/data", headers=auth("manager-token"))

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["audit_ok"] is True
    assert isinstance(allowed.json()["tasks"], list)
