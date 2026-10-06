import json

from apexoperator.agent.runtime import AgentRuntime, AgentTaskRequest
from apexoperator.audit.ledger import CryptographicAuditLedger
from apexoperator.evaluation.models import EvalScenario, ScenarioSeverity
from apexoperator.evaluation.runner import run_scenarios
from apexoperator.policy.engine import DeterministicPolicyEngine, PolicyDecision
from apexoperator.domain.invoice import Invoice
from apexoperator.security.rbac import Permission, RBAC, Role


def test_rbac_matrix():
    assert not RBAC.is_allowed(Role.AP_CLERK, Permission.APPROVAL_APPROVE)
    assert RBAC.is_allowed(Role.FINANCE_MANAGER, Permission.APPROVAL_APPROVE)
    assert RBAC.is_allowed(Role.SYSTEM_ADMIN, Permission.SYSTEM_ADMIN)


def test_policy_threshold_and_math():
    exact = Invoice(
        invoice_id="INV-EXACT",
        vendor_name="Threshold",
        subtotal="4500.00",
        tax="500.00",
        total="5000.00",
    )
    over = Invoice(
        invoice_id="INV-OVER",
        vendor_name="Threshold",
        subtotal="5000.01",
        tax="0.00",
        total="5000.01",
    )
    bad = Invoice(
        invoice_id="INV-BAD",
        vendor_name="Mismatch",
        subtotal="100.00",
        tax="18.00",
        total="119.00",
    )
    assert DeterministicPolicyEngine.evaluate_invoice(exact) == PolicyDecision.AUTO_APPROVED
    assert DeterministicPolicyEngine.evaluate_invoice(over) == PolicyDecision.HUMAN_ESCALATION_REQUIRED
    assert DeterministicPolicyEngine.evaluate_invoice(bad) == PolicyDecision.REJECTED


def test_audit_duplicate_and_tamper_protection():
    ledger = CryptographicAuditLedger()
    ledger.append_event("E1", "A", {"value": 1})
    with __import__("pytest").raises(ValueError):
        ledger.append_event("E1", "B", {"value": 2})
    ledger.chain[0]["event_type"] = "ATTACKED"
    assert ledger.verify_integrity() is False


def test_runtime_step_limit():
    class EndlessPlanner:
        def plan(self, request, state):
            from apexoperator.agent.runtime import PlannedToolCall
            return PlannedToolCall(
                tool_name="missing_tool",
                input_data={},
            )

    runtime = AgentRuntime(__import__("apexoperator.tools.registry", fromlist=["ToolRegistry"]).ToolRegistry(), EndlessPlanner())
    state = runtime.run(
        AgentTaskRequest(task_id="TASK", intent="anything", invoice_id="INV"),
        __import__("apexoperator.tools.registry", fromlist=["ToolContext"]).ToolContext(
            actor_id="eval",
            role=Role.AP_CLERK,
            audit_ledger=CryptographicAuditLedger(),
        ),
    )
    assert state.steps == 3
    assert state.status == "FAILED_RETRY_LIMIT"


def test_eval_runner_reports_required_failures():
    scenarios = [
        EvalScenario("S-PASS", "passing check", ScenarioSeverity.REQUIRED, lambda: None),
        EvalScenario("S-FAIL", "failing check", ScenarioSeverity.REQUIRED, lambda: "blocked"),
        EvalScenario("S-ADVISORY", "advisory failure", ScenarioSeverity.ADVISORY, lambda: "informational"),
    ]
    report = run_scenarios(scenarios)
    assert report.required_total == 2
    assert report.required_passed == 1
    assert report.overall_passed is False
    assert report.score() == 0.5
