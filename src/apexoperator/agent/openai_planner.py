from __future__ import annotations

from typing import Any

from openai import OpenAI

from apexoperator.agent.runtime import (
    AgentTaskRequest,
    AgentTaskState,
    PlannedToolCall,
    PlannerDecision,
)


class OpenAIPlanner:
    """Optional LLM planner; AgentRuntime remains the authority boundary."""

    mode = "openai"

    SYSTEM_PROMPT = """You are the planning component inside ApexOperator.

Your only job is to choose the next governed tool call for a financial operations task.
You do not authorize financial actions, bypass RBAC, change policy, or execute tools yourself.

For process_invoice:
1. Call read_invoice for the requested invoice.
2. Call validate_invoice.
3. Only if validation reports HUMAN_ESCALATION_REQUIRED, call submit_approval.
4. If validation reports AUTO_APPROVED or REJECTED, return no tool.
5. Never change or invent the invoice_id.

For validate_invoice:
- call validate_invoice once, then stop.

Available governed tools:
- read_invoice(invoice_id)
- validate_invoice(invoice_id)
- recalculate_invoice(invoice_id)
- submit_approval(invoice_id, justification)
- verify_audit()

Use the execution history. Return exactly one next tool call or no tool.
"""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-6-astra",
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key is required for OpenAIPlanner")
        self.model = model
        self.client = client or OpenAI(api_key=api_key)

    def _history_text(self, state: AgentTaskState) -> str:
        lines = []
        for item in state.history:
            lines.append(
                f"tool={item.tool_name}; success={item.success}; "
                f"data={item.data!r}; error={item.error!r}"
            )
        return "\n".join(lines) or "(no tool calls yet)"

    def plan(
        self, request: AgentTaskRequest, state: AgentTaskState
    ) -> PlannedToolCall | None:
        prompt = (
            f"task_id={request.task_id}\n"
            f"intent={request.intent}\n"
            f"invoice_id={request.invoice_id}\n"
            f"justification={request.justification or ''}\n"
            f"steps={state.steps}; retries={state.retries}\n"
            f"execution_history:\n{self._history_text(state)}"
        )

        response = self.client.responses.parse(
            model=self.model,
            instructions=self.SYSTEM_PROMPT,
            input=prompt,
            text_format=PlannerDecision,
            max_output_tokens=300,
        )
        decision = response.output_parsed
        if decision is None or decision.tool_name is None:
            return None

        input_data = dict(decision.input_data)
        if decision.tool_name != "verify_audit":
            input_data["invoice_id"] = request.invoice_id

        if decision.tool_name == "submit_approval":
            input_data.setdefault(
                "justification",
                request.justification or "Policy escalation",
            )

        return PlannedToolCall(
            tool_name=decision.tool_name,
            input_data=input_data,
        )
