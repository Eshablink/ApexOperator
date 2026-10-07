import json
import os
from uuid import uuid4

from fastapi.testclient import TestClient

import pytest
from sqlalchemy import text

from apexoperator.persistence.database import init_database, make_engine, make_session_factory
from apexoperator.persistence.models import Base
from apexoperator.api.main import create_app
from apexoperator.persistence.sqlalchemy_audit import SQLAlchemyAuditLedger
from apexoperator.persistence.sqlalchemy_tasks import SQLAlchemyTaskStore


DATABASE_URL = os.getenv("TEST_DATABASE_URL")


pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="TEST_DATABASE_URL is not configured",
)


def test_postgres_task_and_audit_persistence():
    engine = make_engine(DATABASE_URL)
    init_database(engine)
    sessions = make_session_factory(engine)

    suffix = uuid4().hex[:8]
    task_id = f"PG-TASK-{suffix}"
    event_id = f"PG-EVENT-{suffix}"

    tasks = SQLAlchemyTaskStore(sessions)
    audit = SQLAlchemyAuditLedger(sessions)

    tasks.create(
        task_id,
        "INV-PG-001",
        "PENDING_HUMAN_APPROVAL",
        "clerk",
        "HUMAN_ESCALATION_REQUIRED",
        "postgres integration",
    )
    audit.append_event(
        event_id,
        "TEST",
        "postgres_insert",
        {"amount": "6600.00"},
    )

    assert tasks.get(task_id)["status"] == "PENDING_HUMAN_APPROVAL"
    assert audit.verify_integrity()

    with sessions() as session:
        result = session.execute(text("SELECT 1")).scalar_one()
        assert result == 1

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_high_value_task_survives_app_reinitialization(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "incoming_batch.json").write_text(
        json.dumps(
            {
                "invoices": [
                    {
                        "invoice_id": "INV-PG-HIGH-001",
                        "vendor_name": "Persistent Vendor",
                        "subtotal": "6000.00",
                        "tax": "600.00",
                        "total": "6600.00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    app1 = create_app(
        workspace_dir=workspace,
        database_url=DATABASE_URL,
    )
    with TestClient(app1) as client:
        created = client.post(
            "/tasks",
            json={
                "invoice_id": "INV-PG-HIGH-001",
                "justification": "Restart persistence check",
            },
            headers={"Authorization": "Bearer dev-clerk-token"},
        )
        assert created.status_code == 200
        task_id = created.json()["task_id"]
        assert created.json()["status"] == "PENDING_HUMAN_APPROVAL"

    app2 = create_app(
        workspace_dir=workspace,
        database_url=DATABASE_URL,
    )
    with TestClient(app2) as client:
        recovered = client.get(f"/tasks/{task_id}")
        assert recovered.status_code == 200
        assert recovered.json()["status"] == "PENDING_HUMAN_APPROVAL"

    Base.metadata.drop_all(make_engine(DATABASE_URL))
