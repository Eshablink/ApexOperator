import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


GENESIS_HASH = "GENESIS"


class CryptographicAuditLedger:
    """Append-oriented hash chain with explicit integrity verification.

    This provides tamper evidence; it is not a claim of physical immutability.
    Persistence and transactional integration are introduced in later phases.
    """

    def __init__(self) -> None:
        self.chain: list[dict[str, Any]] = []

    @staticmethod
    def _normalize(value: Any) -> Any:
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, float):
            raise TypeError("float values are not permitted in audit payloads")
        if value is None or isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, dict):
            return {
                str(key): CryptographicAuditLedger._normalize(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, (list, tuple)):
            return [CryptographicAuditLedger._normalize(item) for item in value]
        raise TypeError(f"unsupported audit payload type: {type(value).__name__}")

    @classmethod
    def _canonical_json(cls, value: Any) -> bytes:
        return json.dumps(
            cls._normalize(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    def append_event(
        self,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> str:
        event_id = event_id.strip()
        event_type = event_type.strip()
        if not event_id:
            raise ValueError("event_id cannot be empty")
        if not event_type:
            raise ValueError("event_type cannot be empty")
        if any(event["event_id"] == event_id for event in self.chain):
            raise ValueError(f"duplicate event_id: {event_id}")

        previous_hash = self.chain[-1]["current_hash"] if self.chain else GENESIS_HASH
        event = {
            "sequence_id": len(self.chain),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": event_id,
            "event_type": event_type,
            "payload": self._normalize(payload),
            "previous_hash": previous_hash,
        }
        current_hash = hashlib.sha256(self._canonical_json(event)).hexdigest()
        event["current_hash"] = current_hash
        self.chain.append(event)
        return current_hash

    def verify_integrity(self) -> bool:
        seen_event_ids: set[str] = set()

        for index, stored_event in enumerate(self.chain):
            if stored_event.get("sequence_id") != index:
                return False

            event_id = stored_event.get("event_id")
            if not isinstance(event_id, str) or event_id in seen_event_ids:
                return False
            seen_event_ids.add(event_id)

            expected_previous = (
                self.chain[index - 1].get("current_hash")
                if index > 0
                else GENESIS_HASH
            )
            if stored_event.get("previous_hash") != expected_previous:
                return False

            current_hash = stored_event.get("current_hash")
            if not isinstance(current_hash, str):
                return False

            event_without_hash = {
                key: value
                for key, value in stored_event.items()
                if key != "current_hash"
            }
            recalculated_hash = hashlib.sha256(
                self._canonical_json(event_without_hash)
            ).hexdigest()

            if recalculated_hash != current_hash:
                return False

        return True
