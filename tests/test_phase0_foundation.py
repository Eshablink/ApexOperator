from decimal import Decimal
import pytest

from apexoperator.domain.invoice import Invoice
from apexoperator.policy.engine import DeterministicPolicyEngine

def test_invoice_money_is_decimal():
    invoice = Invoice(invoice_id="INV-0001", subtotal="100.00", tax="18.00", total="118.00")
    assert invoice.total == Decimal("118.00")

def test_native_float_is_rejected_for_money():
    with pytest.raises(ValueError):
        Invoice(invoice_id="INV-0002", subtotal=100.0, tax="18.00", total="118.00")

def test_auto_approval_boundary():
    invoice = Invoice(invoice_id="INV-0003", subtotal="4500.00", tax="500.00", total="5000.00")
    assert DeterministicPolicyEngine().evaluate(invoice).decision == "AUTO_APPROVE"

def test_over_limit_escalates():
    invoice = Invoice(invoice_id="INV-0004", subtotal="5000.01", tax="0.00", total="5000.01")
    assert DeterministicPolicyEngine().evaluate(invoice).decision == "HUMAN_ESCALATION_REQUIRED"

def test_total_mismatch_is_not_auto_approved():
    invoice = Invoice(invoice_id="INV-0005", subtotal="100.00", tax="18.00", total="119.00")
    assert DeterministicPolicyEngine().evaluate(invoice).decision == "RECALCULATE_AND_APPROVE"
