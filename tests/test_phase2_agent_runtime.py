import json

from apexoperator.agent.runtime import AgentRuntime, AgentTaskRequest, AgentTaskState, PlannedToolCall
from apexoperator.audit.ledger import CryptographicAuditLedger
from apexoperator.security.rbac import Permission, RBAC, Role
from apexoperator.tools.finance import FinanceToolset, build_finance_tools
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
    for tool in build_finance_tools(finance):
        registry.register(tool)
    return registry


def test_rbac_ap_clerk_cannot_approve():
    assert RBAC.is_allowed(Role.AP_CLERK, Permission.APPROVAL_APPROVE) is False


def test_system_admin_has_all_permissions():
    assert all(RBAC.is_allowed(Role.SYSTEM_ADMIN, permission) for permission in Permission)


def test_registry_blocks_unauthorized_tool_and_audits_denial(tmp_path):
    registry = make_registry(tmp_path)
    context = make_context(Role.FINANCE_MANAGER)
    result = registry.execute_tool(
        "submit_approval",
        {"invoice_id": "INV-001", "justification": "threshold"},
        context,
    )
    assert result.success is False
    assert result.error == "permission_denied"
    assert result.audit_event_hash is not None
    assert context.audit_ledger.verify_integrity() is True


def test_registry_validates_typed_input_and_audits_invalid_call(tmp_path):
    registry = make_registry(tmp_path)
    context = make_context()
    result = registry.execute_tool("read_invoice", {"invoice_id": ""}, context)
    assert result.success is False
    assert result.error.startswith("invalid_input:")
    assert context.audit_ledger.verify_integrity() is True
    assert len(context.audit_ledger.chain) == 1


def test_successful_tool_is_audited(tmp_path):
    registry = make_registry(tmp_path)
    context = make_context()
    result = registry.execute_tool("read_invoice", {"invoice_id": "INV-001"}, context)
    assert result.success is True
    assert result.data["total"] == "6600.00"
    assert context.audit_ledger.verify_integrity() is True
    assert len(context.audit_ledger.chain) == 1


def test_finance_toolset_registers_expected_tools(tmp_path):
    registry = make_registry(tmp_path)
    assert registry.list_tools() == (
        "read_invoice",
        "recalculate_invoice",
        "submit_approval",
        "validate_invoice",
        "verify_audit",
    )


def test_manager_can_verify_audit(tmp_path):
    registry = make_registry(tmp_path)
    context = make_context(Role.FINANCE_MANAGER)
    result = registry.execute_tool("verify_audit", {}, context)
    assert result.success is True
    assert result.data == {"integrity_valid": True}


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


class AlwaysFailPlanner:
    def plan(self, request, state):
        return PlannedToolCall(
            tool_name="missing_tool",
            input_data={},
        )


def test_runtime_stops_after_retry_limit(tmp_path):
    registry = make_registry(tmp_path)
    context = make_context()
    state = AgentRuntime(registry, planner=AlwaysFailPlanner()).run(
        AgentTaskRequest(
            task_id="TASK-002",
            intent="anything",
            invoice_id="INV-001",
        ),
        context,
    )
    assert state.status == "FAILED_RETRY_LIMIT"
    assert state.steps == 3
    assert state.retries == 3
