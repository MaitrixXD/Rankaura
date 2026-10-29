"""
Rate limiter — per-adapter, sleep-based.

Each adapter gets its own limiter instance so different sources can have
different delays. Thread-safe via a simple lock.
"""

from __future__ import annotations

import threading
import time
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)


class RateLimiter:
    """
    Enforces a minimum delay between successive calls.

    Usage:
        limiter = RateLimiter(delay=0.4)
        limiter.wait()   # blocks if called too soon
        do_request()
    """

    def __init__(self, delay: float = 0.4):
        self._delay = delay
        self._last_call: float = 0.0
        self._lock = threading.Lock()

    @property
    def delay(self) -> float:
        return self._delay

    def wait(self) -> None:
        """Block until enough time has passed since the last call."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._delay:
                sleep_for = self._delay - elapsed
                time.sleep(sleep_for)
            self._last_call = time.monotonic()


class RequestBudget:
    """
    Global request counter.

    Tracks total requests across all adapters against a configurable cap.
    Thread-safe. When exhausted, callers should stop making requests.
    """

    def __init__(self, max_requests: int = 500):
        self._max = max_requests
        self._count = 0
        self._lock = threading.Lock()

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self._max - self._count)

    @property
    def used(self) -> int:
        with self._lock:
            return self._count

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def consume(self, n: int = 1) -> bool:
        """
        Try to consume n requests from the budget.

        Returns True if allowed, False if budget would be exceeded.
        """
        with self._lock:
            if self._count + n > self._max:
                log.warning(
                    "Request budget exhausted (%d/%d used)", self._count, self._max
                )
                return False
            self._count += n
            return True

    def reset(self) -> None:
        with self._lock:
            self._count = 0
