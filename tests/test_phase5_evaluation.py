from pathlib import Path

import pytest

from apexoperator.agent.runtime import AgentRuntime, AgentTaskRequest, PlannedToolCall
from apexoperator.audit.ledger import CryptographicAuditLedger
from apexoperator.domain.invoice import Invoice
from apexoperator.evaluation.runner import run_scenarios
from apexoperator.evaluation.models import EvalScenario, ScenarioSeverity
from apexoperator.evaluation.security import run_security_evaluation
from apexoperator.policy.engine import DeterministicPolicyEngine, PolicyDecision
from apexoperator.security.rbac import Permission, RBAC, Role
from apexoperator.tools.finance import InvoiceIdInput
from apexoperator.tools.registry import RegisteredTool, ToolContext, ToolRegistry


def test_rbac_matrix():
    assert not RBAC.is_allowed(Role.AP_CLERK, Permission.APPROVAL_APPROVE)
    assert RBAC.is_allowed(Role.FINANCE_MANAGER, Permission.APPROVAL_APPROVE)
    assert RBAC.is_allowed(Role.SYSTEM_ADMIN, Permission.SYSTEM_ADMIN)


def test_policy_threshold_and_math():
    exact = Invoice(
        invoice_id="INV-EXACT", vendor_name="Threshold",
        subtotal="4500.00", tax="500.00", total="5000.00",
    )
    over = Invoice(
        invoice_id="INV-OVER", vendor_name="Threshold",
        subtotal="5000.01", tax="0.00", total="5000.01",
    )
    bad = Invoice(
        invoice_id="INV-BAD", vendor_name="Mismatch",
        subtotal="100.00", tax="18.00", total="119.00",
    )
    assert DeterministicPolicyEngine.evaluate_invoice(exact) == PolicyDecision.AUTO_APPROVED
    assert DeterministicPolicyEngine.evaluate_invoice(over) == PolicyDecision.HUMAN_ESCALATION_REQUIRED
    assert DeterministicPolicyEngine.evaluate_invoice(bad) == PolicyDecision.REJECTED


def test_audit_duplicate_and_tamper_protection():
    ledger = CryptographicAuditLedger()
    ledger.append_event("E1", "A", {"value": 1})
    with pytest.raises(ValueError, match="duplicate event_id"):
        ledger.append_event("E1", "B", {"value": 2})
    ledger.chain[0]["event_type"] = "ATTACKED"
    assert ledger.verify_integrity() is False


def test_runtime_retry_limit_is_bounded():
    class EndlessPlanner:
        def plan(self, request, state):
            return PlannedToolCall(
                tool_name="read_invoice",
                input_data={"invoice_id": request.invoice_id},
            )

    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            name="read_invoice",
            input_model=InvoiceIdInput,
            permission=Permission.INVOICE_READ,
            handler=lambda _model, _context: (_ for _ in ()).throw(
                ValueError("simulated tool failure")
            ),
        )
    )

    runtime = AgentRuntime(registry, EndlessPlanner())
    context = ToolContext(
        actor_id="eval",
        role=Role.AP_CLERK,
        audit_ledger=CryptographicAuditLedger(),
    )
    state = runtime.run(
        AgentTaskRequest(task_id="TASK", intent="process_invoice", invoice_id="INV"),
        context,
    )
    assert state.steps == 3
    assert state.status == "FAILED_RETRY_LIMIT"


def test_eval_runner_reports_required_failures():
    scenarios = [
        EvalScenario("S-PASS", "passing", ScenarioSeverity.REQUIRED, lambda: None),
        EvalScenario("S-FAIL", "failing", ScenarioSeverity.REQUIRED, lambda: "blocked"),
        EvalScenario("S-ADVISORY", "advisory", ScenarioSeverity.ADVISORY, lambda: "informational"),
    ]
    report = run_scenarios(scenarios)
    assert report.required_total == 2
    assert report.required_passed == 1
    assert report.overall_passed is False
    assert report.score() == 0.5


def test_security_evaluation_has_no_failures(tmp_path):
    assert run_security_evaluation(Path(tmp_path)) == []
