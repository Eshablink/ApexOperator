from pydantic import BaseModel, ConfigDict, field_validator
from apexoperator.portal.browser import LocalInvoicePortal
from apexoperator.security.rbac import Permission
from apexoperator.tools.registry import RegisteredTool

class PortalInvoiceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_id: str
    @field_validator("invoice_id")
    @classmethod
    def validate_invoice_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("invoice_id cannot be empty")
        return value

class PortalSubmitInput(PortalInvoiceInput):
    pass

def build_portal_tools(portal: LocalInvoicePortal):
    return (
        RegisteredTool("portal_read_invoice", PortalInvoiceInput, Permission.INVOICE_READ, lambda model, _ctx: portal.read_invoice(model.invoice_id)),
        RegisteredTool("portal_submit_invoice", PortalSubmitInput, Permission.APPROVAL_SUBMIT, lambda model, _ctx: portal.submit_invoice(model.invoice_id)),
    )
