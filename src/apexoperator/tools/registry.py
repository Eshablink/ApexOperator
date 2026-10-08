from dataclasses import dataclass
from uuid import uuid4
from typing import Any, Callable, Type

from pydantic import BaseModel, ValidationError

from apexoperator.audit.ledger import CryptographicAuditLedger
from apexoperator.security.rbac import Permission, RBAC, Role


class ToolResult(BaseModel):
    success: bool
    tool_name: str
    data: Any = None
    error: str | None = None
    audit_event_hash: str | None = None


@dataclass(frozen=True)
class ToolContext:
    actor_id: str
    role: Role
    audit_ledger: CryptographicAuditLedger
    task_id: str | None = None


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    input_model: Type[BaseModel]
    permission: Permission
    handler: Callable[[BaseModel, ToolContext], Any]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        if not tool.name.strip():
            raise ValueError("tool name cannot be empty")
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool registration: {tool.name}")
        self._tools[tool.name] = tool

    def list_tools(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def execute_tool(self, name: str, input_data: dict[str, Any], context: ToolContext) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(success=False, tool_name=name, error="tool_not_found")

        if not RBAC.is_allowed(context.role, tool.permission):
            event_hash = context.audit_ledger.append_event(
                f"tool-denied:{uuid4()}",
                "TOOL_DENIED",
                {
                    "actor_id": context.actor_id,
                    "role": context.role.value,
                    "task_id": context.task_id,
                    "tool": name,
                    "permission": tool.permission.value,
                },
            )
            return ToolResult(
                success=False,
                tool_name=name,
                error="permission_denied",
                audit_event_hash=event_hash,
            )

        try:
            model = tool.input_model.model_validate(input_data)
        except ValidationError as exc:
            event_hash = context.audit_ledger.append_event(
                f"tool-invalid-input:{uuid4()}",
                "TOOL_INVALID_INPUT",
                {
                    "actor_id": context.actor_id,
                    "role": context.role.value,
                    "task_id": context.task_id,
                    "tool": name,
                },
            )
            return ToolResult(
                success=False,
                tool_name=name,
                error=f"invalid_input: {exc.errors()}",
                audit_event_hash=event_hash,
            )

        event_id = f"tool:{uuid4()}"
        try:
            data = tool.handler(model, context)
            event_hash = context.audit_ledger.append_event(
                event_id,
                "TOOL_EXECUTED",
                {
                    "actor_id": context.actor_id,
                    "role": context.role.value,
                    "task_id": context.task_id,
                    "tool": name,
                    "success": True,
                    "data": data,
                },
            )
            return ToolResult(success=True, tool_name=name, data=data, audit_event_hash=event_hash)
        except Exception as exc:
            event_hash = context.audit_ledger.append_event(
                event_id,
                "TOOL_FAILED",
                {
                    "actor_id": context.actor_id,
                    "role": context.role.value,
                    "task_id": context.task_id,
                    "tool": name,
                    "success": False,
                    "error_type": type(exc).__name__,
                },
            )
            return ToolResult(
                success=False,
                tool_name=name,
                error=f"tool_error: {type(exc).__name__}: {exc}",
                audit_event_hash=event_hash,
            )
