import json
from pathlib import Path

from apexoperator.audit.ledger import CryptographicAuditLedger
from apexoperator.persistence.tasks import TaskStore
from apexoperator.security.rbac import Permission, RBAC, Role
from apexoperator.tools.registry import RegisteredTool, ToolContext, ToolRegistry
from apexoperator.tools.finance import FinanceToolset, InvoiceIdInput, build_finance_tools
from apexoperator.portal.tools import PortalInvoiceInput


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "incoming_batch.json").write_text(
        json.dumps(
            {
                "invoices": [
                    {
                        "invoice_id": "INV-LOW-001",
                        "vendor_name": "Acme",
                        "subtotal": "1000.00",
                        "tax": "100.00",
                        "total": "1100.00",
                    },
                    {
                        "invoice_id": "INV-HIGH-001",
                        "vendor_name": "Enterprise",
                        "subtotal": "6000.00",
                        "tax": "600.00",
                        "total": "6600.00",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return workspace


def run_security_evaluation(tmp_path: Path) -> list[str]:
    failures: list[str] = []

    if RBAC.is_allowed(Role.AP_CLERK, Permission.APPROVAL_APPROVE):
        failures.append("clerk_can_approve")

    if RBAC.is_allowed(Role.AP_CLERK, Permission.SYSTEM_ADMIN):
        failures.append("clerk_has_admin_permission")

    if not RBAC.is_allowed(Role.SYSTEM_ADMIN, Permission.AUDIT_VERIFY):
        failures.append("admin_missing_audit_permission")

    ledger = CryptographicAuditLedger()
    ledger.append_event("E1", "A", {"value": 1})
    ledger.append_event("E2", "B", {"value": 2})
    ledger.chain[0]["payload"]["value"] = 99
    if ledger.verify_integrity():
        failures.append("tampered_memory_ledger_verified")

    registry = ToolRegistry()

    def _never_run(_model, _context):
        raise AssertionError("unauthorized handler executed")

    registry.register(
        RegisteredTool(
            name="admin_only",
            input_model=InvoiceIdInput,
            permission=Permission.SYSTEM_ADMIN,
            handler=_never_run,
        )
    )
    ctx = ToolContext("attacker", Role.AP_CLERK, CryptographicAuditLedger())
    denied = registry.execute_tool(
        "admin_only",
        {"invoice_id": "INV-LOW-001"},
        ctx,
    )
    if denied.success or denied.error != "permission_denied":
        failures.append("registry_authorization_bypass")

    if len(ctx.audit_ledger.chain) != 1 or not ctx.audit_ledger.verify_integrity():
        failures.append("authorization_denial_not_audited")

    workspace = _workspace(tmp_path)
    finance = FinanceToolset(workspace)
    for tool in build_finance_tools(finance):
        if tool.permission is Permission.SYSTEM_ADMIN:
            failures.append(f"finance_tool_overprivileged:{tool.name}")

    task_store = TaskStore(tmp_path / "tasks.sqlite3")
    task_store.create(
        "TASK-SEC-1",
        "INV-HIGH-001",
        "PENDING_HUMAN_APPROVAL",
        "clerk",
        "HUMAN_ESCALATION_REQUIRED",
        None,
    )
    if task_store.transition_review(
        "TASK-SEC-1",
        from_status="APPROVED",
        to_status="REJECTED",
        reviewer="attacker",
        review_comment="bypass",
    ):
        failures.append("invalid_state_transition_allowed")

    task_store.close()
    return failures
