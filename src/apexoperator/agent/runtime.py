from typing import Any, Protocol

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
                return PlannedToolCall(
                    tool_name="submit_approval",
                    input_data={
                        "invoice_id": request.invoice_id,
                        "justification": request.justification or "Policy escalation",
                    },
                )
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

    def run(self, request: AgentTaskRequest, context: ToolContext) -> AgentTaskState:
        state = AgentTaskState(task_id=request.task_id)
        pending_call: PlannedToolCall | None = None

        while state.steps < self.MAX_STEPS:
            if pending_call is None:
                pending_call = self.planner.plan(request, state)
                if pending_call is None:
                    state.status = "COMPLETED"
                    return state

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
