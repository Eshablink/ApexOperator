from decimal import Decimal

import pytest
from pydantic import ValidationError

from apexoperator.audit.ledger import CryptographicAuditLedger
from apexoperator.domain.invoice import Invoice
from apexoperator.policy.engine import (
    DeterministicPolicyEngine,
    PolicyDecision,
)


def make_invoice(**overrides):
    data = {
        "invoice_id": "INV-0001",
        "vendor_name": "Acme Corp",
        "subtotal": "100.00",
        "tax": "18.00",
        "total": "118.00",
    }
    data.update(overrides)
    return Invoice(**data)


def test_invoice_money_is_decimal():
    invoice = make_invoice()
    assert invoice.total == Decimal("118.00")


def test_native_float_is_rejected_for_money():
    with pytest.raises(ValidationError):
        make_invoice(subtotal=100.0)


@pytest.mark.parametrize("field", ["subtotal", "tax", "total"])
def test_negative_money_is_rejected(field):
    with pytest.raises(ValidationError):
        make_invoice(**{field: "-1.00"})


def test_empty_text_is_rejected():
    with pytest.raises(ValidationError):
        make_invoice(vendor_name="   ")


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_invoice(unexpected="value")


def test_exact_auto_approval_boundary():
    invoice = make_invoice(subtotal="4500.00", tax="500.00", total="5000.00")
    assert (
        DeterministicPolicyEngine.evaluate_invoice(invoice)
        == PolicyDecision.AUTO_APPROVED
    )


def test_over_limit_escalates():
    invoice = make_invoice(subtotal="5000.01", tax="0.00", total="5000.01")
    assert (
        DeterministicPolicyEngine.evaluate_invoice(invoice)
        == PolicyDecision.HUMAN_ESCALATION_REQUIRED
    )


def test_total_mismatch_is_rejected():
    invoice = make_invoice(total="119.00")
    assert (
        DeterministicPolicyEngine.evaluate_invoice(invoice)
        == PolicyDecision.REJECTED
    )


def test_ledger_builds_and_verifies_chain():
    ledger = CryptographicAuditLedger()
    h1 = ledger.append_event(
        "EVT-001",
        "INVOICE_SUBMITTED",
        {"id": "INV-0001", "total": Decimal("118.00")},
    )
    h2 = ledger.append_event(
        "EVT-002",
        "POLICY_EVALUATED",
        {"decision": PolicyDecision.AUTO_APPROVED.value},
    )

    assert len(ledger.chain) == 2
    assert ledger.chain[0]["current_hash"] == h1
    assert ledger.chain[1]["previous_hash"] == h1
    assert ledger.chain[1]["current_hash"] == h2
    assert ledger.verify_integrity() is True


def test_ledger_detects_payload_tampering():
    ledger = CryptographicAuditLedger()
    ledger.append_event("EVT-001", "INVOICE_SUBMITTED", {"id": "INV-0001"})
    ledger.append_event("EVT-002", "POLICY_EVALUATED", {"decision": "AUTO_APPROVED"})

    ledger.chain[0]["payload"]["id"] = "TAMPERED"
    assert ledger.verify_integrity() is False


def test_ledger_detects_reordering():
    ledger = CryptographicAuditLedger()
    ledger.append_event("EVT-001", "A", {"value": 1})
    ledger.append_event("EVT-002", "B", {"value": 2})
    ledger.chain.reverse()

    assert ledger.verify_integrity() is False


def test_ledger_detects_sequence_tampering():
    ledger = CryptographicAuditLedger()
    ledger.append_event("EVT-001", "A", {"value": 1})
    ledger.chain[0]["sequence_id"] = 99

    assert ledger.verify_integrity() is False


def test_ledger_detects_hash_tampering():
    ledger = CryptographicAuditLedger()
    ledger.append_event("EVT-001", "A", {"value": 1})
    ledger.chain[0]["current_hash"] = "0" * 64

    assert ledger.verify_integrity() is False


def test_duplicate_event_id_is_rejected():
    ledger = CryptographicAuditLedger()
    ledger.append_event("EVT-001", "A", {"value": 1})

    with pytest.raises(ValueError, match="duplicate event_id"):
        ledger.append_event("EVT-001", "B", {"value": 2})


def test_float_payload_is_rejected():
    ledger = CryptographicAuditLedger()

    with pytest.raises(TypeError, match="float"):
        ledger.append_event("EVT-001", "A", {"amount": 10.5})


def test_empty_ledger_is_valid():
    assert CryptographicAuditLedger().verify_integrity() is True
