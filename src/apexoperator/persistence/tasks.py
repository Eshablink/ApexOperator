import sqlite3
from pathlib import Path
from typing import Any


class TaskStore:
    def __init__(self, database_path: str | Path) -> None:
        self.connection = sqlite3.connect(str(database_path))
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    invoice_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    justification TEXT,
                    reviewer TEXT,
                    review_comment TEXT
                );
                """
            )

    def create(
        self,
        task_id: str,
        invoice_id: str,
        status: str,
        requested_by: str,
        decision: str,
        justification: str | None,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO tasks (
                    task_id, invoice_id, status, requested_by,
                    decision, justification
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    invoice_id,
                    status,
                    requested_by,
                    decision,
                    justification,
                ),
            )

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        return dict(row) if row else None

    def transition_review(
        self,
        task_id: str,
        *,
        from_status: str,
        to_status: str,
        reviewer: str,
        review_comment: str | None,
    ) -> bool:
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE tasks
                SET status = ?, reviewer = ?, review_comment = ?
                WHERE task_id = ? AND status = ?
                """,
                (
                    to_status,
                    reviewer,
                    review_comment,
                    task_id,
                    from_status,
                ),
            )
            return cursor.rowcount == 1

    def close(self) -> None:
        self.connection.close()
