import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
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


    def list_events(self, *, task_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise ValueError("audit event limit must be between 1 and 1000")
        with self.session_factory() as session:
            rows = session.scalars(
                select(AuditEventRecord).order_by(AuditEventRecord.sequence_id.asc()).limit(limit)
            ).all()
            events = []
            for row in rows:
                state = row.after_state if isinstance(row.after_state, dict) else {}
                if task_id is not None and state.get("task_id") != task_id:
                    continue
                events.append({
                    "sequence_id": row.sequence_id,
                    "event_id": row.event_id,
                    "timestamp": row.timestamp,
                    "event_type": row.event_type,
                    "action": row.action,
                    "after_state": state,
                    "previous_hash": row.previous_hash,
                    "event_hash": row.event_hash,
                })
            return events

    def simulate_tamper(self) -> dict[str, Any]:
        events = self.list_events(limit=1000)
        if not events:
            return {"simulated_tamper_detected": False, "reason": "no_events"}
        tampered = [dict(event) for event in events]
        tampered[0]["after_state"] = dict(tampered[0]["after_state"])
        tampered[0]["after_state"]["__tampered_demo__"] = True
        previous = GENESIS_HASH
        detected = False
        for index, event in enumerate(tampered):
            if event["sequence_id"] != index or event["previous_hash"] != previous:
                detected = True
                break
            candidate = {
                "sequence_id": event["sequence_id"],
                "timestamp": event["timestamp"],
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "action": event["action"],
                "after_state": event["after_state"],
                "previous_hash": event["previous_hash"],
            }
            if self._hash_event(candidate) != event["event_hash"]:
                detected = True
                break
            previous = event["event_hash"]
        return {
            "simulated_tamper_detected": detected,
            "persisted_chain_unchanged": self.verify_integrity(),
            "sample_sequence_id": tampered[0]["sequence_id"],
        }

    def reset_demo(self) -> None:
        with self.session_factory.begin() as session:
            session.query(AuditEventRecord).delete()
            meta = session.get(AuditLedgerMeta, 1)
            if meta is None:
                session.add(AuditLedgerMeta(singleton=1, head_sequence_id=-1, head_event_hash=GENESIS_HASH))
            else:
                meta.head_sequence_id = -1
                meta.head_event_hash = GENESIS_HASH

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
