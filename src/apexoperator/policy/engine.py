from decimal import Decimal
from apexoperator.domain.invoice import Invoice

AUTO_APPROVAL_LIMIT = Decimal("5000.00")

class PolicyDecision:
    def __init__(self, decision: str, reason: str):
        self.decision = decision
        self.reason = reason

class DeterministicPolicyEngine:
    def evaluate(self, invoice: Invoice) -> PolicyDecision:
        expected_total = invoice.subtotal + invoice.tax
        if invoice.total != expected_total:
            return PolicyDecision("RECALCULATE_AND_APPROVE", "Invoice total does not equal subtotal plus tax.")
        if invoice.total <= AUTO_APPROVAL_LIMIT:
            return PolicyDecision("AUTO_APPROVE", "Invoice is within the automatic approval limit.")
        return PolicyDecision("HUMAN_ESCALATION_REQUIRED", "Invoice exceeds the automatic approval limit.")
