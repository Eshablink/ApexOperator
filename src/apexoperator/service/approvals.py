from typing import Any

from fastapi import HTTPException
from uuid import uuid4

from apexoperator.agent.runtime import AgentRuntime, AgentTaskRequest, Planner
from apexoperator.api.schemas import ApprovalRequest, CreateTaskRequest, TaskDetailResponse, TaskResponse, TaskStatus
from apexoperator.persistence.sqlalchemy_tasks import SQLAlchemyTaskStore
from apexoperator.persistence.task_evidence import SQLAlchemyTaskEvidenceStore
from apexoperator.security.auth import Principal
from apexoperator.security.rbac import Permission, RBAC
from apexoperator.tools.finance import FinanceToolset, build_finance_tools
from apexoperator.tools.registry import ToolContext, ToolRegistry


class ApprovalService:
    def __init__(
        self,
        *,
        workspace_dir: str,
        task_store: SQLAlchemyTaskStore,
        audit_ledger: Any,
        planner: Planner | None = None,
        planners: dict[str, Planner] | None = None,
        default_planner_mode: str = "mock",
        planner_model: str | None = None,
        task_evidence_store: SQLAlchemyTaskEvidenceStore | None = None,
    ) -> None:
        self.task_store = task_store
        self.audit_ledger = audit_ledger
        self.registry = ToolRegistry()
        finance = FinanceToolset(workspace_dir)
        for tool in build_finance_tools(finance):
            self.registry.register(tool)

        self.planners = dict(planners or {})
        if planner is not None and not self.planners:
            self.planners["mock"] = planner
        if "mock" not in self.planners:
            from apexoperator.agent.runtime import MockPlanner

            self.planners["mock"] = MockPlanner()
        self.default_planner_mode = default_planner_mode if default_planner_mode in self.planners else "mock"
        self.planner_model = planner_model
        self.task_evidence_store = task_evidence_store

        self.runtime = AgentRuntime(
            self.registry,
            planner=self.planners[self.default_planner_mode],
        )

    def _context(self, principal: Principal, task_id: str | None = None) -> ToolContext:
        return ToolContext(
            actor_id=principal.actor_id,
            role=principal.role,
            audit_ledger=self.audit_ledger,
            task_id=task_id,
        )

    @staticmethod
    def _validation_result(state):
        return next(
            (
                result
                for result in reversed(state.history)
                if result.tool_name == "validate_invoice" and result.success
            ),
            None,
        )

    def _resolve_planner(self, requested_mode: str | None) -> tuple[str, Planner, bool]:
        mode = requested_mode or self.default_planner_mode
        if mode in self.planners:
            return mode, self.planners[mode], False
        return "mock", self.planners["mock"], True

    def create_task(self, request: CreateTaskRequest, principal: Principal) -> TaskResponse:
        task_id = str(uuid4())
        mode, planner, fallback = self._resolve_planner(request.planner_mode)
        runtime = AgentRuntime(self.registry, planner=planner)
        state = runtime.run(
            AgentTaskRequest(
                task_id=task_id,
                intent="process_invoice",
                invoice_id=request.invoice_id,
                justification=request.justification,
            ),
            self._context(principal, task_id),
        )

        if state.status == "FAILED_PLANNER":
            if mode == "openai" and "mock" in self.planners:
                fallback = True
                mode = "mock"
                state = AgentRuntime(self.registry, planner=self.planners["mock"]).run(
                    AgentTaskRequest(
                        task_id=task_id,
                        intent="process_invoice",
                        invoice_id=request.invoice_id,
                        justification=request.justification,
                    ),
                    self._context(principal, task_id),
                )
            else:
                raise HTTPException(status_code=502, detail="planner unavailable")
        if state.status == "FAILED_INVALID_PLAN":
            raise HTTPException(status_code=422, detail="planner produced an invalid plan")

        validation = self._validation_result(state)
        if validation is None:
            first_failure = next((item for item in state.history if not item.success), None)
            if first_failure and first_failure.error and "not found" in first_failure.error:
                raise HTTPException(status_code=404, detail=first_failure.error)
            if first_failure and first_failure.error == "permission_denied":
                raise HTTPException(status_code=403, detail="permission denied")
            detail = first_failure.error if first_failure else state.status
            raise HTTPException(status_code=422, detail=detail)

        decision = validation.data["decision"]
        status = {
            "AUTO_APPROVED": TaskStatus.AUTO_APPROVED,
            "REJECTED": TaskStatus.REJECTED,
            "HUMAN_ESCALATION_REQUIRED": TaskStatus.PENDING_HUMAN_APPROVAL,
        }.get(decision)
        if status is None:
            raise HTTPException(status_code=422, detail="unsupported policy decision")

        if status is TaskStatus.PENDING_HUMAN_APPROVAL:
            approval = next(
                (item for item in reversed(state.history) if item.tool_name == "submit_approval"),
                None,
            )
            if approval is None or not approval.success:
                if approval and approval.error == "permission_denied":
                    raise HTTPException(status_code=403, detail="permission denied")
                raise HTTPException(
                    status_code=422,
                    detail=approval.error if approval else "approval submission missing",
                )

        self.task_store.create(
            task_id,
            request.invoice_id,
            status.value,
            principal.actor_id,
            decision,
            request.justification,
        )

        policy_decision = {
            "decision": decision,
            "status": status.value,
            "threshold": "₹5,000",
            "rationale": {
                "AUTO_APPROVED": "Invoice is consistent and within the deterministic threshold.",
                "HUMAN_ESCALATION_REQUIRED": "Invoice exceeds the deterministic threshold.",
                "REJECTED": "Invoice math or source data is inconsistent.",
            }.get(decision, "Deterministic application policy"),
        }
        if self.task_evidence_store is not None:
            self.task_evidence_store.create(
                task_id=task_id,
                planner_mode=mode,
                planner_model=self.planner_model if mode == "openai" else None,
                planner_fallback=fallback,
                proposals=[
                    {
                        "step": index,
                        "tool_name": proposal.tool_name,
                        "input_data": proposal.input_data,
                    }
                    for index, proposal in enumerate(state.planner_proposals, start=1)
                ],
                policy_decision=policy_decision,
            )

        self.audit_ledger.append_event(
            str(uuid4()),
            "TASK_CREATED",
            "task_created",
            {
                "task_id": task_id,
                "invoice_id": request.invoice_id,
                "status": status.value,
                "decision": decision,
                "requested_by": principal.actor_id,
                "planner_mode": mode,
                "planner_fallback": fallback,
            },
        )
        row = self.task_store.get(task_id)
        return TaskResponse.model_validate(row)

    def get_task(self, task_id: str) -> TaskResponse:
        row = self.task_store.get(task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="task not found")
        return TaskResponse.model_validate(row)

    def get_task_detail(self, task_id: str) -> TaskDetailResponse:
        task = self.get_task(task_id)
        evidence = self.task_evidence_store.get(task_id) if self.task_evidence_store is not None else None
        evidence = evidence or {
            "task_id": task_id,
            "planner_mode": "unknown",
            "planner_model": None,
            "planner_fallback": False,
            "proposals": [],
            "policy_decision": {"decision": task.decision},
            "created_at": "",
        }
        return TaskDetailResponse(
            task=task,
            planner=evidence,
            audit_timeline=self.audit_ledger.list_events(task_id=task_id),
        )

    def review_task(
        self,
        task_id: str,
        request: ApprovalRequest,
        principal: Principal,
        *,
        approve: bool,
    ) -> TaskResponse:
        permission = Permission.APPROVAL_APPROVE if approve else Permission.APPROVAL_REJECT
        if not RBAC.is_allowed(principal.role, permission):
            raise HTTPException(status_code=403, detail="permission denied")

        row = self.task_store.get(task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="task not found")
        if row["status"] != TaskStatus.PENDING_HUMAN_APPROVAL.value:
            raise HTTPException(
                status_code=409,
                detail="task already decided; review actions are idempotent",
            )

        target_status = TaskStatus.APPROVED if approve else TaskStatus.REJECTED
        event_type = "HUMAN_APPROVAL_GRANTED" if approve else "HUMAN_APPROVAL_REJECTED"
        self.audit_ledger.append_event(
            str(uuid4()),
            event_type,
            event_type.lower(),
            {
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
            raise HTTPException(
                status_code=409,
                detail="task already decided by another reviewer",
            )

        result = self.get_task(task_id)
        if not self.audit_ledger.verify_integrity():
            raise HTTPException(status_code=500, detail="audit integrity failure")
        return result

    def verify_audit(self, principal: Principal) -> dict[str, bool]:
        if not RBAC.is_allowed(principal.role, Permission.AUDIT_VERIFY):
            raise HTTPException(status_code=403, detail="permission denied")
        return {"integrity_valid": self.audit_ledger.verify_integrity()}

    def simulate_tampering(self, principal: Principal) -> dict[str, bool]:
        if not RBAC.is_allowed(principal.role, Permission.AUDIT_VERIFY):
            raise HTTPException(status_code=403, detail="permission denied")
        return {"tampered": self.audit_ledger.simulate_tampering()}

    def reset_demo_data(self, principal: Principal) -> dict[str, bool]:
        if not RBAC.is_allowed(principal.role, Permission.SYSTEM_ADMIN):
            raise HTTPException(status_code=403, detail="permission denied")
        self.task_store.delete_all()
        if self.task_evidence_store is not None:
            self.task_evidence_store.delete_all()
        self.audit_ledger.reset_for_demo()
        return {"reset": True}
