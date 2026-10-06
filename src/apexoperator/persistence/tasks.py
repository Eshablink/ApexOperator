import sqlite3
from pathlib import Path
from typing import Any


class TaskStore:
    """SQLite task repository using short-lived connections for web-thread safety."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._create_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _create_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
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
        with self._connect() as connection:
            connection.execute(
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
        with self._connect() as connection:
            row = connection.execute(
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
        with self._connect() as connection:
            cursor = connection.execute(
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
        # Connections are intentionally short-lived per operation.
        return None
