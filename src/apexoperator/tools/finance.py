import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from apexoperator.domain.invoice import Invoice
from apexoperator.policy.engine import DeterministicPolicyEngine


class InvoiceIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_id: str

    @field_validator("invoice_id")
    @classmethod
    def require_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("invoice_id cannot be empty")
        return value


class RecalculateInvoiceInput(InvoiceIdInput):
    pass


class SubmitApprovalInput(InvoiceIdInput):
    justification: str

    @field_validator("justification")
    @classmethod
    def require_justification(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("justification cannot be empty")
        return value


class FinanceToolset:
    def __init__(self, workspace_dir: str | Path = "workspace") -> None:
        self.workspace_dir = Path(workspace_dir)

    def _load_invoice(self, invoice_id: str) -> Invoice:
        raw = json.loads((self.workspace_dir / "incoming_batch.json").read_text(encoding="utf-8"))
        records = raw.get("invoices", raw)
        if not isinstance(records, list):
            raise ValueError("incoming_batch.json must contain an invoice list")
        for record in records:
            if isinstance(record, dict) and record.get("invoice_id") == invoice_id:
                return Invoice.model_validate(record)
        raise ValueError(f"invoice not found: {invoice_id}")

    def read_invoice(self, input_data: InvoiceIdInput) -> dict[str, Any]:
        invoice = self._load_invoice(input_data.invoice_id)
        return {
            "invoice_id": invoice.invoice_id,
            "vendor_name": invoice.vendor_name,
            "subtotal": str(invoice.subtotal),
            "tax": str(invoice.tax),
            "total": str(invoice.total),
        }

    def validate_invoice(self, input_data: InvoiceIdInput) -> dict[str, str]:
        invoice = self._load_invoice(input_data.invoice_id)
        decision = DeterministicPolicyEngine.evaluate_invoice(invoice)
        return {"invoice_id": invoice.invoice_id, "decision": decision.value}

    def recalculate_invoice(self, input_data: RecalculateInvoiceInput) -> dict[str, str | bool]:
        invoice = self._load_invoice(input_data.invoice_id)
        recalculated_total = invoice.subtotal + invoice.tax
        return {
            "invoice_id": invoice.invoice_id,
            "recalculated_total": str(recalculated_total),
            "previous_total": str(invoice.total),
            "matches": invoice.total == recalculated_total,
        }

    def submit_approval(self, input_data: SubmitApprovalInput) -> dict[str, str]:
        invoice = self._load_invoice(input_data.invoice_id)
        decision = DeterministicPolicyEngine.evaluate_invoice(invoice)
        if decision.value != "HUMAN_ESCALATION_REQUIRED":
            raise ValueError("approval submission is only valid for human-escalation invoices")
        return {
            "invoice_id": invoice.invoice_id,
            "status": "PENDING_HUMAN_APPROVAL",
            "justification": input_data.justification,
        }
