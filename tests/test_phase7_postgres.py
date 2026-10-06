import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from apexoperator.persistence.database import init_database, make_engine, make_session_factory
from apexoperator.persistence.models import Base
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
