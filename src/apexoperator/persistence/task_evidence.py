from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import sessionmaker

from apexoperator.persistence.models import TaskEvidenceRecord


class SQLAlchemyTaskEvidenceStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def create(
        self,
        *,
        task_id: str,
        planner_mode: str,
        planner_model: str | None,
        planner_fallback: bool,
        proposals: list[dict[str, Any]],
        policy_decision: dict[str, Any] | None,
    ) -> None:
        with self.session_factory.begin() as session:
            session.add(
                TaskEvidenceRecord(
                    task_id=task_id,
                    planner_mode=planner_mode,
                    planner_model=planner_model,
                    planner_fallback=planner_fallback,
                    proposals=proposals,
                    policy_decision=policy_decision,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.get(TaskEvidenceRecord, task_id)
            if row is None:
                return None
            return {
                "task_id": row.task_id,
                "planner_mode": row.planner_mode,
                "planner_model": row.planner_model,
                "planner_fallback": row.planner_fallback,
                "proposals": row.proposals or [],
                "policy_decision": row.policy_decision,
                "created_at": row.created_at,
            }

    def delete_all(self) -> None:
        with self.session_factory.begin() as session:
            session.query(TaskEvidenceRecord).delete(synchronize_session=False)

    def close(self) -> None:
        return None
