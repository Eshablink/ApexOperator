from decimal import Decimal
from enum import Enum

from apexoperator.domain.invoice import Invoice


class PolicyDecision(str, Enum):
    AUTO_APPROVED = "AUTO_APPROVED"
    HUMAN_ESCALATION_REQUIRED = "HUMAN_ESCALATION_REQUIRED"
    REJECTED = "REJECTED"


class DeterministicPolicyEngine:
    AUTO_APPROVAL_THRESHOLD = Decimal("5000.00")

    @classmethod
    def evaluate_invoice(cls, invoice: Invoice) -> PolicyDecision:
        calculated_total = invoice.subtotal + invoice.tax
        if invoice.total != calculated_total:
            return PolicyDecision.REJECTED

        if invoice.total > cls.AUTO_APPROVAL_THRESHOLD:
            return PolicyDecision.HUMAN_ESCALATION_REQUIRED

        return PolicyDecision.AUTO_APPROVED
