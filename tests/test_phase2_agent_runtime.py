import json

from apexoperator.agent.runtime import AgentRuntime, AgentTaskRequest
from apexoperator.audit.ledger import CryptographicAuditLedger
from apexoperator.security.rbac import Permission, RBAC, Role
from apexoperator.tools.finance import FinanceToolset, InvoiceIdInput, SubmitApprovalInput
from apexoperator.tools.registry import RegisteredTool, ToolContext, ToolRegistry


def make_context(role=Role.AP_CLERK):
    return ToolContext(
        actor_id="tester",
        role=role,
        audit_ledger=CryptographicAuditLedger(),
    )


def make_registry(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "incoming_batch.json").write_text(
        json.dumps(
            {
                "invoices": [
                    {
                        "invoice_id": "INV-001",
                        "vendor_name": "Acme",
                        "subtotal": "6000.00",
                        "tax": "600.00",
                        "total": "6600.00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    finance = FinanceToolset(workspace)
    registry = ToolRegistry()
    registry.register(RegisteredTool(
        "read_invoice", InvoiceIdInput, Permission.INVOICE_READ,
        lambda model, _ctx: finance.read_invoice(model),
    ))
    registry.register(RegisteredTool(
        "validate_invoice", InvoiceIdInput, Permission.INVOICE_VALIDATE,
        lambda model, _ctx: finance.validate_invoice(model),
    ))
    registry.register(RegisteredTool(
        "submit_approval", SubmitApprovalInput, Permission.APPROVAL_SUBMIT,
        lambda model, _ctx: finance.submit_approval(model),
    ))
    return registry


def test_rbac_ap_clerk_cannot_approve():
    assert RBAC.is_allowed(Role.AP_CLERK, Permission.APPROVAL_APPROVE) is False


def test_system_admin_has_all_permissions():
    assert all(RBAC.is_allowed(Role.SYSTEM_ADMIN, permission) for permission in Permission)


def test_registry_blocks_unauthorized_tool(tmp_path):
    registry = make_registry(tmp_path)
    result = registry.execute_tool(
        "submit_approval",
        {"invoice_id": "INV-001", "justification": "threshold"},
        make_context(Role.FINANCE_MANAGER),
    )
    assert result.success is False
    assert result.error == "permission_denied"


def test_registry_validates_typed_input(tmp_path):
    registry = make_registry(tmp_path)
    result = registry.execute_tool(
        "read_invoice",
        {"invoice_id": ""},
        make_context(),
    )
    assert result.success is False
    assert result.error.startswith("invalid_input:")


def test_successful_tool_is_audited(tmp_path):
    registry = make_registry(tmp_path)
    context = make_context()
    result = registry.execute_tool("read_invoice", {"invoice_id": "INV-001"}, context)
    assert result.success is True
    assert result.data["total"] == "6600.00"
    assert context.audit_ledger.verify_integrity() is True
    assert len(context.audit_ledger.chain) == 1


def test_runtime_is_bounded_and_processes_invoice(tmp_path):
    registry = make_registry(tmp_path)
    context = make_context()
    state = AgentRuntime(registry).run(
        AgentTaskRequest(
            task_id="TASK-001",
            intent="process_invoice",
            invoice_id="INV-001",
            justification="Invoice exceeds automatic approval threshold.",
        ),
        context,
    )
    assert state.status == "COMPLETED"
    assert state.steps == 3
    assert all(result.success for result in state.history)
    assert context.audit_ledger.verify_integrity() is True
    assert len(context.audit_ledger.chain) == 3
