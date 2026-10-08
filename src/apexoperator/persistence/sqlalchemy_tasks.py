from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from apexoperator.persistence.models import TaskRecord


class SQLAlchemyTaskStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def create(self, task_id: str, organization_id: str, invoice_id: str, status: str, requested_by: str, decision: str, justification: str | None) -> None:
        with self.session_factory.begin() as session:
            session.add(TaskRecord(task_id=task_id, organization_id=organization_id, invoice_id=invoice_id, status=status, requested_by=requested_by, decision=decision, justification=justification))

    def get_by_invoice_id(self, invoice_id: str, organization_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.scalars(select(TaskRecord).where(TaskRecord.invoice_id == invoice_id, TaskRecord.organization_id == organization_id).order_by(TaskRecord.created_at.desc())).first()
            return self._dict(row) if row else None

    def get(self, task_id: str, organization_id: str | None = None) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.get(TaskRecord, task_id)
            if row is None or (organization_id is not None and row.organization_id != organization_id):
                return None
            return self._dict(row)

    def list_recent(self, limit: int = 50, *, organization_id: str = "default", requested_by: str | None = None) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            query = select(TaskRecord).where(TaskRecord.organization_id == organization_id)
            if requested_by is not None:
                query = query.where(TaskRecord.requested_by == requested_by)
            rows = session.scalars(query.order_by(TaskRecord.created_at.desc()).limit(limit)).all()
            return [self._dict(row) for row in rows]

    def transition_review(self, task_id: str, *, organization_id: str, from_status: str, to_status: str, reviewer: str, review_comment: str | None) -> bool:
        with self.session_factory.begin() as session:
            result = session.execute(update(TaskRecord).where(TaskRecord.task_id == task_id, TaskRecord.organization_id == organization_id, TaskRecord.status == from_status).values(status=to_status, reviewer=reviewer, review_comment=review_comment))
            return result.rowcount == 1

    @staticmethod
    def _dict(row: TaskRecord) -> dict[str, Any]:
        return {"task_id": row.task_id, "invoice_id": row.invoice_id, "status": row.status, "requested_by": row.requested_by, "decision": row.decision, "justification": row.justification, "reviewer": row.reviewer, "review_comment": row.review_comment}

    def close(self) -> None:
        return None
