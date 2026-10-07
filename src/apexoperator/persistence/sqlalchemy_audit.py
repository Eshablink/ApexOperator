import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from apexoperator.persistence.models import AuditEventRecord, AuditLedgerMeta


GENESIS_HASH = "GENESIS"


class SQLAlchemyAuditLedger:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory
        self._ensure_meta()

    def _ensure_meta(self) -> None:
        with self.session_factory.begin() as session:
            if session.get(AuditLedgerMeta, 1) is None:
                session.add(
                    AuditLedgerMeta(
                        singleton=1,
                        head_sequence_id=-1,
                        head_event_hash=GENESIS_HASH,
                    )
                )

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
                str(k): SQLAlchemyAuditLedger._normalize(v)
                for k, v in sorted(value.items(), key=lambda p: str(p[0]))
            }
        if isinstance(value, (list, tuple)):
            return [SQLAlchemyAuditLedger._normalize(v) for v in value]
        raise TypeError(f"unsupported audit data type: {type(value).__name__}")

    @classmethod
    def _canonical(cls, value: Any) -> bytes:
        return json.dumps(
            cls._normalize(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @classmethod
    def _hash_event(cls, event: dict[str, Any]) -> str:
        return hashlib.sha256(cls._canonical(event)).hexdigest()

    def append_event(
        self,
        event_id: str,
        event_type: str,
        action_or_payload: str | dict[str, Any],
        after_state: dict[str, Any] | None = None,
    ) -> str:
        event_id = event_id.strip()
        event_type = event_type.strip()
        if after_state is None and isinstance(action_or_payload, dict):
            action = "event"
            after_state = action_or_payload
        elif after_state is not None and isinstance(action_or_payload, str):
            action = action_or_payload.strip()
        else:
            raise ValueError("audit action/payload arguments are invalid")
        if not action:
            raise ValueError("audit action cannot be empty")
        if not event_id or not event_type or not action:
            raise ValueError("event identifiers and action cannot be empty")

        try:
            with self.session_factory.begin() as session:
                meta = session.get(AuditLedgerMeta, 1)
                if meta is None:
                    raise RuntimeError("audit metadata missing")

                sequence_id = meta.head_sequence_id + 1
                previous_hash = meta.head_event_hash
                timestamp = datetime.now(timezone.utc)
                normalized = self._normalize(after_state)
                event = {
                    "sequence_id": sequence_id,
                    "timestamp": timestamp.isoformat(),
                    "event_id": event_id,
                    "event_type": event_type,
                    "action": action,
                    "after_state": normalized,
                    "previous_hash": previous_hash,
                }
                event_hash = self._hash_event(event)

                session.add(
                    AuditEventRecord(
                        sequence_id=sequence_id,
                        event_id=event_id,
                        timestamp=timestamp.isoformat(),
                        event_type=event_type,
                        action=action,
                        after_state=normalized,
                        previous_hash=previous_hash,
                        event_hash=event_hash,
                    )
                )
                meta.head_sequence_id = sequence_id
                meta.head_event_hash = event_hash
                return event_hash
        except IntegrityError as exc:
            raise ValueError(f"duplicate or conflicting audit event: {event_id}") from exc

    def verify_integrity(self) -> bool:
        with self.session_factory() as session:
            rows = session.scalars(
                select(AuditEventRecord).order_by(AuditEventRecord.sequence_id.asc())
            ).all()
            previous = GENESIS_HASH
            seen: set[str] = set()

            for index, row in enumerate(rows):
                if row.sequence_id != index or row.event_id in seen:
                    return False
                seen.add(row.event_id)
                if row.previous_hash != previous:
                    return False

                event = {
                    "sequence_id": row.sequence_id,
                    "timestamp": row.timestamp,
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "action": row.action,
                    "after_state": row.after_state,
                    "previous_hash": row.previous_hash,
                }
                if self._hash_event(event) != row.event_hash:
                    return False
                previous = row.event_hash

            meta = session.get(AuditLedgerMeta, 1)
            if meta is None:
                return False
            expected_seq = len(rows) - 1
            expected_hash = previous if rows else GENESIS_HASH
            return (
                meta.head_sequence_id == expected_seq
                and meta.head_event_hash == expected_hash
            )


    def list_for_task(self, task_id: str) -> list[dict[str, Any]]:
        task_id = task_id.strip()
        if not task_id:
            return []
        with self.session_factory() as session:
            rows = session.scalars(
                select(AuditEventRecord).order_by(AuditEventRecord.sequence_id.asc())
            ).all()
            events: list[dict[str, Any]] = []
            for row in rows:
                state = row.after_state if isinstance(row.after_state, dict) else {}
                if state.get("task_id") != task_id:
                    continue
                events.append(
                    {
                        "sequence_id": row.sequence_id,
                        "timestamp": row.timestamp,
                        "event_id": row.event_id,
                        "event_type": row.event_type,
                        "action": row.action,
                        "after_state": state,
                        "previous_hash": row.previous_hash,
                        "event_hash": row.event_hash,
                    }
                )
            return events

    def export_events(self) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(AuditEventRecord).order_by(AuditEventRecord.sequence_id.asc())
            ).all()
            return [
                {
                    "sequence_id": row.sequence_id,
                    "timestamp": row.timestamp,
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "action": row.action,
                    "after_state": row.after_state,
                    "previous_hash": row.previous_hash,
                    "event_hash": row.event_hash,
                }
                for row in rows
            ]

    def simulate_tampering(self, task_id: str | None = None) -> dict[str, Any]:
        events = self.list_for_task(task_id) if task_id else self.export_events()
        if not events:
            raise ValueError("no audit events available for tamper demo")

        target_id = events[0]["sequence_id"]
        with self.session_factory.begin() as session:
            row = session.get(AuditEventRecord, target_id)
            if row is None:
                raise ValueError("audit event disappeared before tamper demo")
            state = dict(row.after_state) if isinstance(row.after_state, dict) else {"value": row.after_state}
            state["tamper_demo"] = "UNAUTHORIZED_MUTATION"
            row.after_state = state
        return {
            "tampered_sequence_id": target_id,
            "integrity_valid": self.verify_integrity(),
        }

    def reset(self) -> None:
        with self.session_factory.begin() as session:
            session.execute(delete(AuditEventRecord))
            meta = session.get(AuditLedgerMeta, 1)
            if meta is None:
                session.add(
                    AuditLedgerMeta(
                        singleton=1,
                        head_sequence_id=-1,
                        head_event_hash=GENESIS_HASH,
                    )
                )
            else:
                meta.head_sequence_id = -1
                meta.head_event_hash = GENESIS_HASH
