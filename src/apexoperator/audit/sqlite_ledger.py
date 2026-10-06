import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


GENESIS_HASH = "GENESIS"


class SQLiteAuditLedger:
    """Persistent, append-oriented audit ledger with tamper-evident hash chaining.

    The ledger detects modifications, deletions, insertions, and reordering of
    stored events through sequence/hash validation plus a persisted chain head.
    It is tamper-evident, not physically immutable.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    @staticmethod
    def _normalize(value: Any) -> Any:
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, float):
            raise TypeError("float values are not permitted in audit data")
        if value is None or isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, dict):
            return {
                str(key): SQLiteAuditLedger._normalize(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, (list, tuple)):
            return [SQLiteAuditLedger._normalize(item) for item in value]
        raise TypeError(f"unsupported audit data type: {type(value).__name__}")

    @classmethod
    def _canonical_json(cls, value: Any) -> str:
        return json.dumps(
            cls._normalize(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def _hash_event(cls, event: dict[str, Any]) -> str:
        return hashlib.sha256(cls._canonical_json(event).encode("utf-8")).hexdigest()

    def _create_schema(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence_id INTEGER PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    after_state TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS audit_ledger_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    head_sequence_id INTEGER NOT NULL,
                    head_event_hash TEXT NOT NULL
                );

                INSERT OR IGNORE INTO audit_ledger_meta (
                    singleton, head_sequence_id, head_event_hash
                ) VALUES (1, -1, ?);
                """,
                (GENESIS_HASH,),
            )

    def append_event(
        self,
        event_id: str,
        event_type: str,
        action: str,
        after_state: dict[str, Any],
    ) -> str:
        event_id = event_id.strip()
        event_type = event_type.strip()
        action = action.strip()

        if not event_id:
            raise ValueError("event_id cannot be empty")
        if not event_type:
            raise ValueError("event_type cannot be empty")
        if not action:
            raise ValueError("action cannot be empty")

        try:
            with self.connection:
                row = self.connection.execute(
                    "SELECT head_sequence_id, head_event_hash "
                    "FROM audit_ledger_meta WHERE singleton = 1"
                ).fetchone()
                assert row is not None

                sequence_id = int(row["head_sequence_id"]) + 1
                previous_hash = str(row["head_event_hash"])
                timestamp = datetime.now(timezone.utc).isoformat()
                normalized_state = self._normalize(after_state)

                event = {
                    "sequence_id": sequence_id,
                    "timestamp": timestamp,
                    "event_id": event_id,
                    "event_type": event_type,
                    "action": action,
                    "after_state": normalized_state,
                    "previous_hash": previous_hash,
                }
                event_hash = self._hash_event(event)

                self.connection.execute(
                    """
                    INSERT INTO audit_events (
                        sequence_id, event_id, timestamp, event_type,
                        action, after_state, previous_hash, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sequence_id,
                        event_id,
                        timestamp,
                        event_type,
                        action,
                        self._canonical_json(normalized_state),
                        previous_hash,
                        event_hash,
                    ),
                )
                self.connection.execute(
                    """
                    UPDATE audit_ledger_meta
                    SET head_sequence_id = ?, head_event_hash = ?
                    WHERE singleton = 1
                    """,
                    (sequence_id, event_hash),
                )
                return event_hash
        except sqlite3.IntegrityError as exc:
            if "event_id" in str(exc):
                raise ValueError(f"duplicate event_id: {event_id}") from exc
            raise

    def verify_integrity(self) -> bool:
        rows = self.connection.execute(
            """
            SELECT sequence_id, event_id, timestamp, event_type,
                   action, after_state, previous_hash, event_hash
            FROM audit_events
            ORDER BY sequence_id ASC
            """
        ).fetchall()

        seen_ids: set[str] = set()
        expected_previous = GENESIS_HASH

        for expected_sequence, row in enumerate(rows):
            if row["sequence_id"] != expected_sequence:
                return False

            event_id = row["event_id"]
            if event_id in seen_ids:
                return False
            seen_ids.add(event_id)

            if row["previous_hash"] != expected_previous:
                return False

            try:
                after_state = json.loads(row["after_state"])
            except (TypeError, json.JSONDecodeError):
                return False

            event = {
                "sequence_id": row["sequence_id"],
                "timestamp": row["timestamp"],
                "event_id": event_id,
                "event_type": row["event_type"],
                "action": row["action"],
                "after_state": after_state,
                "previous_hash": row["previous_hash"],
            }
            if self._hash_event(event) != row["event_hash"]:
                return False

            expected_previous = row["event_hash"]

        meta = self.connection.execute(
            "SELECT head_sequence_id, head_event_hash "
            "FROM audit_ledger_meta WHERE singleton = 1"
        ).fetchone()
        if meta is None:
            return False

        expected_head_sequence = len(rows) - 1
        expected_head_hash = expected_previous if rows else GENESIS_HASH
        return (
            meta["head_sequence_id"] == expected_head_sequence
            and meta["head_event_hash"] == expected_head_hash
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SQLiteAuditLedger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
