from types import SimpleNamespace

import pytest

from apexoperator.agent.openai_planner import OpenAIPlanner
from apexoperator.agent.runtime import (
    AgentRuntime,
    AgentTaskRequest,
    AgentTaskState,
    PlannedToolCall,
)
from apexoperator.audit.ledger import CryptographicAuditLedger
from apexoperator.security.rbac import Role
from apexoperator.tools.finance import FinanceToolset, build_finance_tools
from apexoperator.tools.registry import ToolContext, ToolRegistry


class FakeResponses:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        decision = self.decisions.pop(0)
        return SimpleNamespace(output_parsed=decision)


class FakeClient:
    def __init__(self, decisions):
        self.responses = FakeResponses(decisions)


def make_registry(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "incoming_batch.json").write_text(
        '{"invoices":[{"invoice_id":"INV-HIGH-001","vendor_name":"Acme","subtotal":"6000.00","tax":"600.00","total":"6600.00"}]}',
        encoding="utf-8",
    )
    finance = FinanceToolset(workspace)
    registry = ToolRegistry()
    for tool in build_finance_tools(finance):
        registry.register(tool)
    return registry


def make_context():
    return ToolContext(
        actor_id="tester",
        role=Role.AP_CLERK,
        audit_ledger=CryptographicAuditLedger(),
    )


def test_openai_planner_constrains_invoice_id():
    from apexoperator.agent.runtime import PlannerDecision

    fake = FakeClient([
        PlannerDecision(
            tool_name="read_invoice",
            input_data={"invoice_id": "attacker-invoice"},
        )
    ])
    planner = OpenAIPlanner(
        api_key="unused",
        model="test-model",
        client=fake,
    )
    result = planner.plan(
        AgentTaskRequest(
            task_id="T-1",
            intent="process_invoice",
            invoice_id="INV-HIGH-001",
        ),
        AgentTaskState(task_id="T-1"),
    )

    assert result is not None
    assert result.tool_name == "read_invoice"
    assert result.input_data["invoice_id"] == "INV-HIGH-001"
    assert fake.responses.calls[0]["model"] == "test-model"


def test_openai_planner_can_stop_without_a_tool():
    from apexoperator.agent.runtime import PlannerDecision

    fake = FakeClient([PlannerDecision(tool_name=None)])
    planner = OpenAIPlanner(api_key="unused", client=fake)
    result = planner.plan(
        AgentTaskRequest(
            task_id="T-2",
            intent="process_invoice",
            invoice_id="INV-HIGH-001",
        ),
        AgentTaskState(task_id="T-2", steps=2),
    )
    assert result is None


def test_runtime_rejects_disallowed_planner_tool(tmp_path):
    class BadPlanner:
        def plan(self, request, state):
            return PlannedToolCall(
                tool_name="verify_audit",
                input_data={},
            )

    state = AgentRuntime(make_registry(tmp_path), planner=BadPlanner()).run(
        AgentTaskRequest(
            task_id="T-3",
            intent="process_invoice",
            invoice_id="INV-HIGH-001",
        ),
        make_context(),
    )
    assert state.status == "FAILED_INVALID_PLAN"
    assert state.steps == 0
    assert state.history == []


def test_runtime_completes_low_invoice_without_submit_approval(tmp_path):
    registry = make_registry(tmp_path)
    # Replace fixture with a low-value invoice for this scenario.
    workspace = tmp_path / "workspace"
    (workspace / "incoming_batch.json").write_text(
        '{"invoices":[{"invoice_id":"INV-LOW-001","vendor_name":"Acme","subtotal":"1000.00","tax":"100.00","total":"1100.00"}]}',
        encoding="utf-8",
    )
    finance = FinanceToolset(workspace)
    registry = ToolRegistry()
    for tool in build_finance_tools(finance):
        registry.register(tool)

    state = AgentRuntime(registry).run(
        AgentTaskRequest(
            task_id="T-4",
            intent="process_invoice",
            invoice_id="INV-LOW-001",
        ),
        make_context(),
    )
    assert state.status == "COMPLETED"
    assert [item.tool_name for item in state.history] == [
        "read_invoice",
        "validate_invoice",
    ]
