"""
ServerGen AI — Rate Limiting.

In-memory implementation for the prototype.
Interface is replaceable by Redis/distributed implementation later.

Rate limiting and account lockout are SEPARATE concepts:
- Rate limiting: per-IP/key request throttling
- Account lockout: per-user failed-login security measure
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import defaultdict
from enum import StrEnum
from threading import Lock

from src.core.exceptions import RateLimitExceededError


class RateLimitCategory(StrEnum):
    LOGIN = "login"
    API = "api"
    LLM = "llm"
    TOOL = "tool"


class RateLimitService(ABC):
    """Abstract rate limiter interface."""

    @abstractmethod
    def check(self, category: RateLimitCategory, key: str) -> None:
        """
        Check if the key is within rate limits for the category.
        Raises RateLimitExceededError if limit exceeded.
        """

    @abstractmethod
    def reset(self, category: RateLimitCategory, key: str) -> None:
        """Reset the counter for a key (e.g., after successful auth)."""


# ── In-memory sliding window implementation ─────────────────────────────

_LIMITS: dict[RateLimitCategory, tuple[int, int]] = {
    # (max_requests, window_seconds)
    RateLimitCategory.LOGIN: (10, 300),
    RateLimitCategory.API: (100, 60),
    RateLimitCategory.LLM: (20, 60),
    RateLimitCategory.TOOL: (50, 60),
}


class InMemoryRateLimiter(RateLimitService):
    """
    Sliding window in-memory rate limiter.

    Thread-safe via Lock. Not suitable for multi-process deployments —
    replace with Redis for distributed use.
    """

    def __init__(self) -> None:
        # {category: {key: [timestamps]}}
        self._windows: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self._lock = Lock()

    def check(self, category: RateLimitCategory, key: str) -> None:
        max_req, window_sec = _LIMITS[category]
        now = time.monotonic()

        with self._lock:
            timestamps = self._windows[category][key]
            # Evict expired entries
            cutoff = now - window_sec
            self._windows[category][key] = [t for t in timestamps if t > cutoff]
            timestamps = self._windows[category][key]

            if len(timestamps) >= max_req:
                oldest = timestamps[0]
                retry_after = window_sec - (now - oldest)
                raise RateLimitExceededError(
                    message=f"Rate limit exceeded for {category}",
                    retry_after_seconds=max(0.0, retry_after),
                )

            timestamps.append(now)

    def reset(self, category: RateLimitCategory, key: str) -> None:
        with self._lock:
            self._windows[category][key] = []


# Singleton for the prototype
_rate_limiter = InMemoryRateLimiter()


def get_rate_limiter() -> InMemoryRateLimiter:
    return _rate_limiter
