from uuid import uuid4

from fastapi import HTTPException

from typing import Any
from apexoperator.security.rbac import Permission, RBAC, Role
from apexoperator.tools.finance import FinanceToolset, build_finance_tools
from apexoperator.tools.registry import ToolContext, ToolRegistry

from apexoperator.api.schemas import ApprovalRequest, CreateTaskRequest, TaskResponse, TaskStatus
from apexoperator.persistence.sqlalchemy_tasks import SQLAlchemyTaskStore
from apexoperator.security.auth import Principal


class ApprovalService:
    def __init__(
        self,
        *,
        workspace_dir: str,
        task_store: SQLAlchemyTaskStore,
        audit_ledger: Any,
    ) -> None:
        self.task_store = task_store
        self.audit_ledger = audit_ledger
        finance = FinanceToolset(workspace_dir)
        self.registry = ToolRegistry()
        for tool in build_finance_tools(finance):
            self.registry.register(tool)

    def _context(self, principal: Principal) -> ToolContext:
        return ToolContext(
            actor_id=principal.actor_id,
            role=principal.role,
            audit_ledger=self.audit_ledger,
        )

    def create_task(self, request: CreateTaskRequest, principal: Principal) -> TaskResponse:
        task_id = str(uuid4())
        context = self._context(principal)

        read_result = self.registry.execute_tool(
            "read_invoice",
            {"invoice_id": request.invoice_id},
            context,
        )
        if not read_result.success:
            raise HTTPException(status_code=404, detail=read_result.error)

        validation = self.registry.execute_tool(
            "validate_invoice",
            {"invoice_id": request.invoice_id},
            context,
        )
        if not validation.success:
            raise HTTPException(status_code=422, detail=validation.error)

        decision = validation.data["decision"]
        status = (
            TaskStatus.AUTO_APPROVED
            if decision == "AUTO_APPROVED"
            else TaskStatus.REJECTED
            if decision == "REJECTED"
            else TaskStatus.PENDING_HUMAN_APPROVAL
        )

        if status is TaskStatus.PENDING_HUMAN_APPROVAL:
            approval = self.registry.execute_tool(
                "submit_approval",
                {
                    "invoice_id": request.invoice_id,
                    "justification": request.justification or "Policy escalation",
                },
                context,
            )
            if not approval.success:
                raise HTTPException(status_code=422, detail=approval.error)

        self.task_store.create(
            task_id,
            request.invoice_id,
            status.value,
            principal.actor_id,
            decision,
            request.justification,
        )
        row = self.task_store.get(task_id)
        return TaskResponse.model_validate(row)

    def get_task(self, task_id: str) -> TaskResponse:
        row = self.task_store.get(task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="task not found")
        return TaskResponse.model_validate(row)

    def review_task(
        self,
        task_id: str,
        request: ApprovalRequest,
        principal: Principal,
        *,
        approve: bool,
    ) -> TaskResponse:
        permission = (
            Permission.APPROVAL_APPROVE if approve else Permission.APPROVAL_REJECT
        )
        if not RBAC.is_allowed(principal.role, permission):
            raise HTTPException(status_code=403, detail="permission denied")

        row = self.task_store.get(task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="task not found")
        if row["status"] != TaskStatus.PENDING_HUMAN_APPROVAL.value:
            raise HTTPException(
                status_code=409,
                detail="task is not pending human approval",
            )

        target_status = TaskStatus.APPROVED if approve else TaskStatus.REJECTED
        event_type = "HUMAN_APPROVAL_GRANTED" if approve else "HUMAN_APPROVAL_REJECTED"
        event_hash = self.audit_ledger.append_event(
            event_id=str(uuid4()),
            event_type=event_type,
            payload={
                "task_id": task_id,
                "invoice_id": row["invoice_id"],
                "reviewer": principal.actor_id,
                "comment": request.comment,
                "from_status": row["status"],
                "to_status": target_status.value,
            },
        )

        transitioned = self.task_store.transition_review(
            task_id,
            from_status=TaskStatus.PENDING_HUMAN_APPROVAL.value,
            to_status=target_status.value,
            reviewer=principal.actor_id,
            review_comment=request.comment,
        )
        if not transitioned:
            raise HTTPException(status_code=409, detail="task changed before review")

        result = self.get_task(task_id)
        if not self.audit_ledger.verify_integrity():
            raise HTTPException(status_code=500, detail="audit integrity failure")
        return result

    def verify_audit(self, principal: Principal) -> dict[str, bool]:
        if not RBAC.is_allowed(principal.role, Permission.AUDIT_VERIFY):
            raise HTTPException(status_code=403, detail="permission denied")
        return {"integrity_valid": self.audit_ledger.verify_integrity()}
