from __future__ import annotations

import asyncio
from collections import deque
from random import uniform
from time import monotonic


class RateLimiter:
    def __init__(self, max_requests_per_minute: int, *, jitter_seconds: float = 0.25) -> None:
        if max_requests_per_minute < 1:
            raise ValueError("max_requests_per_minute must be >= 1")
        self.max_requests = max_requests_per_minute
        self.jitter_seconds = jitter_seconds
        self._timestamps: deque[float] = deque()

    def allow(self) -> bool:
        self._discard_old()
        return len(self._timestamps) < self.max_requests

    def wait_seconds(self) -> float:
        self._discard_old()
        if len(self._timestamps) < self.max_requests:
            return uniform(0, self.jitter_seconds)
        return max(0.0, 60.0 - (monotonic() - self._timestamps[0])) + uniform(
            0,
            self.jitter_seconds,
        )

    async def acquire(self) -> None:
        wait_for = self.wait_seconds()
        if wait_for > 0:
            await asyncio.sleep(wait_for)
        self._discard_old()
        self._timestamps.append(monotonic())

    def _discard_old(self) -> None:
        cutoff = monotonic() - 60.0
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

