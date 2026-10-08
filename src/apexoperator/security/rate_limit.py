from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class LoginRateLimiter:
    """Small process-local limiter suitable for the single-instance demo deployment."""

    def __init__(self, *, limit: int = 5, window_seconds: int = 300) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = monotonic()
        with self._lock:
            bucket = self._attempts[key]
            cutoff = now - self.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            remaining = max(0, self.limit - len(bucket))
            if len(bucket) >= self.limit:
                retry_after = max(1, int(bucket[0] + self.window_seconds - now))
                return False, retry_after
            bucket.append(now)
            return True, max(0, remaining - 1)

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)
