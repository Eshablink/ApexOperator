from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from apexoperator.tools.registry import ToolContext, ToolRegistry, ToolResult


class AgentTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    intent: str
    invoice_id: str
    justification: str | None = None


class AgentTaskState(BaseModel):
    task_id: str
    status: str = "RUNNING"
    steps: int = 0
    retries: int = 0
    history: list[ToolResult] = Field(default_factory=list)


class PlannedToolCall(BaseModel):
    tool_name: str
    input_data: dict[str, Any]


class Planner(Protocol):
    def plan(
        self, request: AgentTaskRequest, state: AgentTaskState
    ) -> PlannedToolCall | None:
        ...


AllowedToolName = Literal[
    "read_invoice",
    "validate_invoice",
    "recalculate_invoice",
    "submit_approval",
    "verify_audit",
]


class PlannerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: AllowedToolName | None = None
    input_data: dict[str, Any] = Field(default_factory=dict)


class MockPlanner:
    def plan(
        self, request: AgentTaskRequest, state: AgentTaskState
    ) -> PlannedToolCall | None:
        if request.intent == "process_invoice":
            if state.steps == 0:
                return PlannedToolCall(
                    tool_name="read_invoice",
                    input_data={"invoice_id": request.invoice_id},
                )
            if state.steps == 1:
                return PlannedToolCall(
                    tool_name="validate_invoice",
                    input_data={"invoice_id": request.invoice_id},
                )
            if state.steps == 2:
                validation = next(
                    (
                        item
                        for item in reversed(state.history)
                        if item.tool_name == "validate_invoice" and item.success
                    ),
                    None,
                )
                decision = (validation.data or {}).get("decision") if validation else None
                if decision == "HUMAN_ESCALATION_REQUIRED":
                    return PlannedToolCall(
                        tool_name="submit_approval",
                        input_data={
                            "invoice_id": request.invoice_id,
                            "justification": request.justification or "Policy escalation",
                        },
                    )
                return None
        elif request.intent == "validate_invoice" and state.steps == 0:
            return PlannedToolCall(
                tool_name="validate_invoice",
                input_data={"invoice_id": request.invoice_id},
            )
        return None


class AgentRuntime:
    MAX_STEPS = 5
    MAX_RETRIES = 2

    def __init__(self, registry: ToolRegistry, planner: Planner | None = None) -> None:
        self.registry = registry
        self.planner = planner or MockPlanner()

    @staticmethod
    def _last_successful_validation(state: AgentTaskState) -> str | None:
        for result in reversed(state.history):
            if result.tool_name == "validate_invoice" and result.success:
                return (result.data or {}).get("decision")
        return None

    def _plan_is_allowed(
        self,
        request: AgentTaskRequest,
        state: AgentTaskState,
        call: PlannedToolCall,
    ) -> bool:
        if call.tool_name not in self.registry.list_tools():
            return False

        requested_invoice = call.input_data.get("invoice_id")
        if requested_invoice is not None and requested_invoice != request.invoice_id:
            return False

        if request.intent == "validate_invoice":
            return state.steps == 0 and call.tool_name == "validate_invoice"

        if request.intent != "process_invoice":
            return False

        if state.steps == 0:
            return call.tool_name == "read_invoice"
        if state.steps == 1:
            return call.tool_name == "validate_invoice"
        if state.steps == 2:
            decision = self._last_successful_validation(state)
            return (
                decision == "HUMAN_ESCALATION_REQUIRED"
                and call.tool_name == "submit_approval"
            )
        return False

    def _audit_failure(
        self,
        context: ToolContext,
        *,
        event_id: str,
        event_type: str,
        action: str,
        payload: dict[str, Any],
    ) -> None:
        context.audit_ledger.append_event(event_id, event_type, action, payload)

    def _invalid_plan(
        self, state: AgentTaskState, reason: str, context: ToolContext
    ) -> AgentTaskState:
        state.status = "FAILED_INVALID_PLAN"
        self._audit_failure(
            context,
            event_id=f"planner-invalid:{state.task_id}:{state.steps}",
            event_type="PLANNER_INVALID",
            action="planner_invalid",
            payload={"task_id": state.task_id, "reason": reason},
        )
        return state

    def run(self, request: AgentTaskRequest, context: ToolContext) -> AgentTaskState:
        state = AgentTaskState(task_id=request.task_id)
        pending_call: PlannedToolCall | None = None

        while state.steps < self.MAX_STEPS:
            if pending_call is None:
                try:
                    pending_call = self.planner.plan(request, state)
                except Exception as exc:
                    state.status = "FAILED_PLANNER"
                    self._audit_failure(
                        context,
                        event_id=f"planner-failed:{request.task_id}:{state.steps}",
                        event_type="PLANNER_FAILED",
                        action="planner_failed",
                        payload={
                            "task_id": request.task_id,
                            "error_type": type(exc).__name__,
                        },
                    )
                    return state

                if pending_call is None:
                    self._audit_failure(
                        context,
                        event_id=f"planner-proposal:{request.task_id}:{state.steps}",
                        event_type="PLANNER_PROPOSAL",
                        action="planner_proposal",
                        payload={
                            "task_id": request.task_id,
                            "planner_mode": getattr(self.planner, "mode", type(self.planner).__name__.replace("Planner", "").lower()),
                            "model": getattr(self.planner, "model", None),
                            "proposed_tool": None,
                            "input_data": {},
                        },
                    )
                    state.status = "COMPLETED"
                    return state

                self._audit_failure(
                    context,
                    event_id=f"planner-proposal:{request.task_id}:{state.steps}",
                    event_type="PLANNER_PROPOSAL",
                    action="planner_proposal",
                    payload={
                        "task_id": request.task_id,
                        "planner_mode": getattr(self.planner, "mode", type(self.planner).__name__.replace("Planner", "").lower()),
                        "model": getattr(self.planner, "model", None),
                        "proposed_tool": pending_call.tool_name,
                        "input_data": pending_call.input_data,
                    },
                )

                if not self._plan_is_allowed(request, state, pending_call):
                    return self._invalid_plan(
                        state,
                        f"disallowed_plan:{pending_call.tool_name}",
                        context,
                    )

            result = self.registry.execute_tool(
                pending_call.tool_name,
                pending_call.input_data,
                context,
            )
            state.history.append(result)
            state.steps += 1

            if result.success:
                state.retries = 0
                pending_call = None
                continue

            state.retries += 1
            if state.retries > self.MAX_RETRIES:
                state.status = "FAILED_RETRY_LIMIT"
                return state

        state.status = "FAILED_STEP_LIMIT"
        return state
