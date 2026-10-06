from decimal import Decimal

from sqlalchemy import create_engine

from apexoperator.persistence.database import init_database, make_session_factory
from apexoperator.persistence.models import Base
from apexoperator.persistence.sqlalchemy_audit import SQLAlchemyAuditLedger
from apexoperator.persistence.sqlalchemy_tasks import SQLAlchemyTaskStore


def stack(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'prod.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    init_database(engine)
    sessions = make_session_factory(engine)
    return engine, sessions


def test_sqlalchemy_task_store_round_trip(tmp_path):
    _, sessions = stack(tmp_path)
    store = SQLAlchemyTaskStore(sessions)
    store.create("TASK-1", "INV-1", "PENDING_HUMAN_APPROVAL", "clerk", "HUMAN_ESCALATION_REQUIRED", "review")
    assert store.get("TASK-1")["invoice_id"] == "INV-1"
    assert store.transition_review(
        "TASK-1",
        from_status="PENDING_HUMAN_APPROVAL",
        to_status="APPROVED",
        reviewer="manager",
        review_comment="ok",
    )
    assert store.get("TASK-1")["status"] == "APPROVED"


def test_sqlalchemy_audit_survives_reopen(tmp_path):
    _, sessions = stack(tmp_path)
    ledger = SQLAlchemyAuditLedger(sessions)
    h1 = ledger.append_event("E1", "A", "first", {"amount": Decimal("10.00")})
    h2 = ledger.append_event("E2", "B", "second", {"amount": Decimal("20.00")})
    assert h2 != h1
    assert ledger.verify_integrity()

    reopened = SQLAlchemyAuditLedger(sessions)
    assert reopened.verify_integrity()


def test_sqlalchemy_audit_detects_tampering(tmp_path):
    engine, sessions = stack(tmp_path)
    ledger = SQLAlchemyAuditLedger(sessions)
    ledger.append_event("E1", "A", "first", {"value": 1})

    with sessions.begin() as session:
        row = session.get(__import__("apexoperator.persistence.models", fromlist=["AuditEventRecord"]).AuditEventRecord, 0)
        row.action = "tampered"

    assert not ledger.verify_integrity()
    Base.metadata.drop_all(engine)
