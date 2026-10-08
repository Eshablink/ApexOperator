from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from apexoperator.agent.runtime import AgentRuntime, AgentTaskRequest, Planner
from apexoperator.api.schemas import ApprovalRequest, CreateTaskRequest, TaskResponse, TaskStatus
from apexoperator.domain.invoice import Invoice
from apexoperator.policy.engine import DeterministicPolicyEngine
from apexoperator.persistence.sqlalchemy_tasks import SQLAlchemyTaskStore
from apexoperator.security.auth import Principal
from apexoperator.security.rbac import Permission, RBAC, Role
from apexoperator.tools.finance import FinanceToolset, build_finance_tools
from apexoperator.tools.registry import ToolContext, ToolRegistry


class ApprovalService:
    def __init__(self, *, workspace_dir: str, task_store: SQLAlchemyTaskStore, audit_ledger: Any, planner: Planner | None = None) -> None:
        self.task_store = task_store
        self.audit_ledger = audit_ledger
        self.registry = ToolRegistry()
        for tool in build_finance_tools(FinanceToolset(workspace_dir)):
            self.registry.register(tool)
        self.runtime = AgentRuntime(self.registry, planner=planner)

    def _context(self, principal: Principal) -> ToolContext:
        return ToolContext(actor_id=principal.actor_id, role=principal.role, audit_ledger=self.audit_ledger)

    @staticmethod
    def _validation_result(state):
        return next((result for result in reversed(state.history) if result.tool_name == "validate_invoice" and result.success), None)

    def create_task(self, request: CreateTaskRequest, principal: Principal) -> TaskResponse:
        existing = self.task_store.get_by_invoice_id(request.invoice_id, principal.organization_id)
        if existing is not None:
            return TaskResponse.model_validate(existing)
        task_id = str(uuid4())
        state = self.runtime.run(AgentTaskRequest(task_id=task_id, intent="process_invoice", invoice_id=request.invoice_id, justification=request.justification), self._context(principal))
        if state.status == "FAILED_PLANNER": raise HTTPException(status_code=502, detail="planner unavailable")
        if state.status == "FAILED_INVALID_PLAN": raise HTTPException(status_code=422, detail="planner produced an invalid plan")
        validation = self._validation_result(state)
        if validation is None:
            first_failure = next((item for item in state.history if not item.success), None)
            if first_failure and first_failure.error and "not found" in first_failure.error: raise HTTPException(status_code=404, detail=first_failure.error)
            if first_failure and first_failure.error == "permission_denied": raise HTTPException(status_code=403, detail="permission denied")
            raise HTTPException(status_code=422, detail=first_failure.error if first_failure else state.status)
        decision = validation.data["decision"]
        status = {"AUTO_APPROVED": TaskStatus.AUTO_APPROVED, "REJECTED": TaskStatus.REJECTED, "HUMAN_ESCALATION_REQUIRED": TaskStatus.PENDING_HUMAN_APPROVAL}.get(decision)
        if status is None: raise HTTPException(status_code=422, detail="unsupported policy decision")
        if status is TaskStatus.PENDING_HUMAN_APPROVAL:
            approval = next((item for item in reversed(state.history) if item.tool_name == "submit_approval"), None)
            if approval is None or not approval.success: raise HTTPException(status_code=403 if approval and approval.error == "permission_denied" else 422, detail="permission denied" if approval and approval.error == "permission_denied" else (approval.error if approval else "approval submission missing"))
        try:
            self.task_store.create(task_id, principal.organization_id, request.invoice_id, status.value, principal.actor_id, decision, request.justification)
        except IntegrityError:
            existing = self.task_store.get_by_invoice_id(request.invoice_id, principal.organization_id)
            if existing is None: raise
            return TaskResponse.model_validate(existing)
        return TaskResponse.model_validate(self.task_store.get(task_id, principal.organization_id))

    def create_task_from_document(self, invoice: Invoice, principal: Principal, *, justification: str | None = None, confidence: str = "HIGH") -> TaskResponse:
        existing = self.task_store.get_by_invoice_id(invoice.invoice_id, principal.organization_id)
        if existing is not None: return TaskResponse.model_validate(existing)
        decision = DeterministicPolicyEngine.evaluate_invoice(invoice)
        status = {"AUTO_APPROVED": TaskStatus.AUTO_APPROVED, "REJECTED": TaskStatus.REJECTED, "HUMAN_ESCALATION_REQUIRED": TaskStatus.PENDING_HUMAN_APPROVAL}[decision.value]
        task_id = str(uuid4())
        try:
            self.task_store.create(task_id, principal.organization_id, invoice.invoice_id, status.value, principal.actor_id, decision.value, justification)
        except IntegrityError:
            existing = self.task_store.get_by_invoice_id(invoice.invoice_id, principal.organization_id)
            if existing is None: raise
            return TaskResponse.model_validate(existing)
        self.audit_ledger.append_event(str(uuid4()), "DOCUMENT_PROCESSED", "document.processed", {"task_id": task_id, "organization_id": principal.organization_id, "invoice_id": invoice.invoice_id, "vendor_name": invoice.vendor_name, "subtotal": str(invoice.subtotal), "tax": str(invoice.tax), "total": str(invoice.total), "confidence": confidence, "decision": decision.value, "actor": principal.actor_id})
        return TaskResponse.model_validate(self.task_store.get(task_id, principal.organization_id))

    def get_task(self, task_id: str, principal: Principal) -> TaskResponse:
        row = self.task_store.get(task_id, principal.organization_id)
        if row is None: raise HTTPException(status_code=404, detail="task not found")
        if principal.role == Role.AP_CLERK and row["requested_by"] != principal.actor_id:
            raise HTTPException(status_code=404, detail="task not found")
        return TaskResponse.model_validate(row)

    def list_tasks(self, principal: Principal, limit: int = 50) -> list[dict[str, Any]]:
        owner = principal.actor_id if principal.role == Role.AP_CLERK else None
        return self.task_store.list_recent(limit, organization_id=principal.organization_id, requested_by=owner)

    def review_task(self, task_id: str, request: ApprovalRequest, principal: Principal, *, approve: bool) -> TaskResponse:
        permission = Permission.APPROVAL_APPROVE if approve else Permission.APPROVAL_REJECT
        if not RBAC.is_allowed(principal.role, permission): raise HTTPException(status_code=403, detail="permission denied")
        row = self.task_store.get(task_id, principal.organization_id)
        if row is None: raise HTTPException(status_code=404, detail="task not found")
        if row["status"] != TaskStatus.PENDING_HUMAN_APPROVAL.value: raise HTTPException(status_code=409, detail="task is not pending human approval")
        target_status = TaskStatus.APPROVED if approve else TaskStatus.REJECTED
        event_type = "HUMAN_APPROVAL_GRANTED" if approve else "HUMAN_APPROVAL_REJECTED"
        if not self.task_store.transition_review(task_id, organization_id=principal.organization_id, from_status=TaskStatus.PENDING_HUMAN_APPROVAL.value, to_status=target_status.value, reviewer=principal.actor_id, review_comment=request.comment):
            raise HTTPException(status_code=409, detail="task changed before review")
        try:
            self.audit_ledger.append_event(str(uuid4()), event_type, event_type.lower(), {"task_id": task_id, "organization_id": principal.organization_id, "invoice_id": row["invoice_id"], "reviewer": principal.actor_id, "comment": request.comment, "from_status": row["status"], "to_status": target_status.value})
        except Exception as exc:
            raise HTTPException(status_code=500, detail="audit write failure") from exc
        result = self.get_task(task_id, principal)
        if not self.audit_ledger.verify_integrity(): raise HTTPException(status_code=500, detail="audit integrity failure")
        return result

    def verify_audit(self, principal: Principal) -> dict[str, bool]:
        if not RBAC.is_allowed(principal.role, Permission.AUDIT_VERIFY): raise HTTPException(status_code=403, detail="permission denied")
        return {"integrity_valid": self.audit_ledger.verify_integrity()}
