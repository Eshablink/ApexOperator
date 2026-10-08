from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import sessionmaker

from apexoperator.persistence.models import TaskRecord


class SQLAlchemyTaskStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def create(
        self,
        task_id: str,
        invoice_id: str,
        status: str,
        requested_by: str,
        decision: str,
        justification: str | None,
    ) -> None:
        with self.session_factory.begin() as session:
            session.add(
                TaskRecord(
                    task_id=task_id,
                    invoice_id=invoice_id,
                    status=status,
                    requested_by=requested_by,
                    decision=decision,
                    justification=justification,
                )
            )

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.get(TaskRecord, task_id)
            if row is None:
                return None
            return self._dict(row)

    def list_recent(
        self,
        limit: int = 50,
        *,
        offset: int = 0,
        status: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            statement = select(TaskRecord).order_by(TaskRecord.created_at.desc())
            if status:
                statement = statement.where(TaskRecord.status == status)
            if query:
                term = f"%{query.strip().lower()}%"
                statement = statement.where(
                    or_(
                        func.lower(TaskRecord.task_id).like(term),
                        func.lower(TaskRecord.invoice_id).like(term),
                        func.lower(TaskRecord.status).like(term),
                        func.lower(TaskRecord.requested_by).like(term),
                        func.lower(TaskRecord.reviewer).like(term),
                    )
                )
            rows = session.scalars(statement.offset(max(0, offset)).limit(max(1, min(limit, 100)))).all()
            return [self._dict(row) for row in rows]

    def count(self, *, status: str | None = None, query: str | None = None) -> int:
        with self.session_factory() as session:
            statement = select(func.count()).select_from(TaskRecord)
            if status:
                statement = statement.where(TaskRecord.status == status)
            if query:
                term = f"%{query.strip().lower()}%"
                statement = statement.where(
                    or_(
                        func.lower(TaskRecord.task_id).like(term),
                        func.lower(TaskRecord.invoice_id).like(term),
                        func.lower(TaskRecord.status).like(term),
                        func.lower(TaskRecord.requested_by).like(term),
                        func.lower(TaskRecord.reviewer).like(term),
                    )
                )
            return int(session.scalar(statement) or 0)

    def delete_all(self) -> None:
        with self.session_factory.begin() as session:
            session.execute(delete(TaskRecord))

    def transition_review(
        self,
        task_id: str,
        *,
        from_status: str,
        to_status: str,
        reviewer: str,
        review_comment: str | None,
    ) -> bool:
        with self.session_factory.begin() as session:
            result = session.execute(
                update(TaskRecord)
                .where(
                    TaskRecord.task_id == task_id,
                    TaskRecord.status == from_status,
                )
                .values(
                    status=to_status,
                    reviewer=reviewer,
                    review_comment=review_comment,
                )
            )
            return result.rowcount == 1

    @staticmethod
    def _dict(row: TaskRecord) -> dict[str, Any]:
        return {
            "task_id": row.task_id,
            "invoice_id": row.invoice_id,
            "status": row.status,
            "requested_by": row.requested_by,
            "decision": row.decision,
            "justification": row.justification,
            "reviewer": row.reviewer,
            "review_comment": row.review_comment,
        }

    def close(self) -> None:
        return None
