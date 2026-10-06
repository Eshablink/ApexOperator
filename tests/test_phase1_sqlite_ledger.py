import json
from decimal import Decimal

import pytest

from apexoperator.audit.sqlite_ledger import GENESIS_HASH, SQLiteAuditLedger


def seed_ledger(tmp_path):
    ledger = SQLiteAuditLedger(tmp_path / "audit.sqlite3")
    first = ledger.append_event(
        "EVT-001",
        "INVOICE_SUBMITTED",
        "submit_invoice",
        {"invoice_id": "INV-001", "total": Decimal("118.00")},
    )
    second = ledger.append_event(
        "EVT-002",
        "POLICY_EVALUATED",
        "evaluate_policy",
        {"decision": "AUTO_APPROVED"},
    )
    return ledger, first, second


def test_persistent_ledger_round_trip(tmp_path):
    ledger, first, second = seed_ledger(tmp_path)
    database_path = ledger.database_path
    ledger.close()

    reopened = SQLiteAuditLedger(database_path)
    assert reopened.verify_integrity() is True

    rows = reopened.connection.execute(
        "SELECT sequence_id, previous_hash, event_hash FROM audit_events ORDER BY sequence_id"
    ).fetchall()
    assert rows[0]["sequence_id"] == 0
    assert rows[0]["previous_hash"] == GENESIS_HASH
    assert rows[0]["event_hash"] == first
    assert rows[1]["sequence_id"] == 1
    assert rows[1]["previous_hash"] == first
    assert rows[1]["event_hash"] == second
    reopened.close()


def test_duplicate_event_id_is_rejected(tmp_path):
    ledger, _, _ = seed_ledger(tmp_path)

    with pytest.raises(ValueError, match="duplicate event_id"):
        ledger.append_event(
            "EVT-001",
            "OTHER",
            "other_action",
            {"value": 1},
        )
    ledger.close()


def test_action_tampering_is_detected(tmp_path):
    ledger, _, _ = seed_ledger(tmp_path)
    ledger.connection.execute(
        "UPDATE audit_events SET action = 'tampered' WHERE sequence_id = 0"
    )
    assert ledger.verify_integrity() is False
    ledger.close()


def test_after_state_tampering_is_detected(tmp_path):
    ledger, _, _ = seed_ledger(tmp_path)
    ledger.connection.execute(
        "UPDATE audit_events SET after_state = ? WHERE sequence_id = 0",
        (json.dumps({"invoice_id": "ATTACKED"}),),
    )
    assert ledger.verify_integrity() is False
    ledger.close()


def test_previous_hash_tampering_is_detected(tmp_path):
    ledger, _, _ = seed_ledger(tmp_path)
    ledger.connection.execute(
        "UPDATE audit_events SET previous_hash = 'BAD' WHERE sequence_id = 1"
    )
    assert ledger.verify_integrity() is False
    ledger.close()


def test_event_hash_tampering_is_detected(tmp_path):
    ledger, _, _ = seed_ledger(tmp_path)
    ledger.connection.execute(
        "UPDATE audit_events SET event_hash = ? WHERE sequence_id = 0",
        ("0" * 64,),
    )
    assert ledger.verify_integrity() is False
    ledger.close()


def test_last_event_deletion_is_detected_by_chain_head(tmp_path):
    ledger, _, _ = seed_ledger(tmp_path)
    ledger.connection.execute("DELETE FROM audit_events WHERE sequence_id = 1")
    assert ledger.verify_integrity() is False
    ledger.close()


def test_middle_event_deletion_is_detected(tmp_path):
    ledger, _, _ = seed_ledger(tmp_path)
    ledger.connection.execute("DELETE FROM audit_events WHERE sequence_id = 0")
    assert ledger.verify_integrity() is False
    ledger.close()


def test_sequence_reordering_is_detected(tmp_path):
    ledger, _, _ = seed_ledger(tmp_path)
    ledger.connection.execute(
        "UPDATE audit_events SET sequence_id = 10 WHERE sequence_id = 0"
    )
    assert ledger.verify_integrity() is False
    ledger.close()


def test_insertion_is_detected(tmp_path):
    ledger, _, second = seed_ledger(tmp_path)
    with pytest.raises(Exception):
        ledger.connection.execute(
            """
            INSERT INTO audit_events (
                sequence_id, event_id, timestamp, event_type,
                action, after_state, previous_hash, event_hash
            ) VALUES (2, 'EVT-999', '2026-01-01T00:00:00+00:00',
                      'INJECTED', 'inject', '{}', ?, ?)
            """,
            (second, "0" * 64),
        )
    assert ledger.verify_integrity() is True
    ledger.close()


def test_float_audit_data_is_rejected(tmp_path):
    ledger = SQLiteAuditLedger(tmp_path / "audit.sqlite3")
    with pytest.raises(TypeError, match="float"):
        ledger.append_event(
            "EVT-001",
            "TEST",
            "test",
            {"amount": 10.5},
        )
    ledger.close()
