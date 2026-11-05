"""
In-memory sliding-window rate limiter for failed login attempts.

Limitations & Architecture:
- In-memory & Per-Process: State is stored in memory and is not shared across
  workers or server instances. State resets when the application restarts.
- IP Resolution: Uses `request.client.host` directly. Does NOT trust
  unverified `X-Forwarded-For` headers to prevent header-spoofing bypasses.
  Behind a reverse proxy or load balancer, configure trusted proxy middleware
  (such as Uvicorn's `--proxy-headers` / `--forwarded-allow-ips`) to set
  `request.client` safely.
- Memory Bounded: Keyed by (normalised_email, client_ip). State for inactive
  or expired keys is purged opportunistically and via `purge_stale()`.
"""

from collections import deque
import logging
import math
import threading
import time
from typing import Callable, Optional

from fastapi import HTTPException, status

logger = logging.getLogger("helpdesk_api")


def mask_email(email: str) -> str:
    """Mask email for safe logging (e.g., 'ra***r@example.com' or 'a***@example.com')."""
    clean = email.strip()
    if "@" in clean:
        local, domain = clean.split("@", 1)
        if len(local) <= 1:
            masked_local = "*"
        elif len(local) <= 3:
            masked_local = local[0] + "***"
        else:
            masked_local = local[:2] + "***" + local[-1]
        return f"{masked_local}@{domain}"
    if len(clean) <= 2:
        return "***"
    return clean[:2] + "***"


class LoginRateLimiter:
    """
    Thread-safe sliding-window rate limiter for tracking failed login attempts.

    Keyed by (normalised_email, client_ip).
    Only records FAILED attempts. A successful login resets the key.
    After max_attempts within window_seconds, subsequent attempts are rejected
    with HTTP 429 and Retry-After header for lockout_seconds.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 300,
        lockout_seconds: int = 300,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._clock = clock or time.time
        self._lock = threading.Lock()
        self._failures: dict[tuple[str, str], deque[float]] = {}
        self._locked_until: dict[tuple[str, str], float] = {}

    def _normalize_key(self, email: str, ip: str) -> tuple[str, str]:
        return (email.strip().lower(), ip.strip())

    def _prune_failures(self, key: tuple[str, str], now: float) -> None:
        """Remove failures outside the sliding window for key."""
        if key in self._failures:
            cutoff = now - self.window_seconds
            dq = self._failures[key]
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if not dq:
                del self._failures[key]

    def is_locked(self, email: str, ip: str) -> tuple[bool, int]:
        """
        Check if the key is currently locked out.
        Returns (is_locked, retry_after_seconds).
        """
        key = self._normalize_key(email, ip)
        now = self._clock()

        with self._lock:
            # 1. Check active lockout
            if key in self._locked_until:
                lockout_end = self._locked_until[key]
                if now < lockout_end:
                    remaining = max(1, int(math.ceil(lockout_end - now)))
                    return True, remaining
                # Lockout expired
                del self._locked_until[key]
                self._failures.pop(key, None)
                return False, 0

            # 2. Check sliding window failures
            self._prune_failures(key, now)
            if key in self._failures and len(self._failures[key]) >= self.max_attempts:
                # Key reached threshold
                lockout_end = now + self.lockout_seconds
                self._locked_until[key] = lockout_end
                remaining = self.lockout_seconds
                return True, remaining

            return False, 0

    def check_and_raise_if_locked(self, email: str, ip: str) -> None:
        """
        Raise HTTP 429 if key is locked out.
        Includes Retry-After header and {detail, retry_after_seconds} body.
        """
        locked, retry_after = self.is_locked(email, ip)
        if locked:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "detail": "Too many failed sign-in attempts. Please try again later.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

    def record_failure(self, email: str, ip: str) -> bool:
        """
        Record a failed login attempt.
        Returns True if this attempt resulted in a new lockout.
        """
        key = self._normalize_key(email, ip)
        now = self._clock()

        with self._lock:
            self._prune_failures(key, now)
            if key not in self._failures:
                self._failures[key] = deque()

            self._failures[key].append(now)

            if len(self._failures[key]) >= self.max_attempts and key not in self._locked_until:
                lockout_end = now + self.lockout_seconds
                self._locked_until[key] = lockout_end
                logger.warning(
                    "Login rate limit reached: account locked for ip=%s, email=%s for %ds",
                    key[1],
                    mask_email(key[0]),
                    self.lockout_seconds,
                )
                return True

            return False

    def reset(self, email: str, ip: str) -> None:
        """Reset failed attempt counters and lockout for a key on successful login."""
        key = self._normalize_key(email, ip)
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def purge_stale(self) -> int:
        """
        Purge expired lockout and failure entries to keep memory bounded.
        Returns count of keys completely removed.
        """
        now = self._clock()
        purged = 0
        with self._lock:
            # Purge expired lockouts
            expired_locks = [k for k, end in self._locked_until.items() if now >= end]
            for k in expired_locks:
                del self._locked_until[k]
                if k in self._failures:
                    del self._failures[k]
                purged += 1

            # Purge expired failure deques
            all_keys = list(self._failures.keys())
            for k in all_keys:
                self._prune_failures(k, now)
                if k not in self._failures and k not in self._locked_until:
                    purged += 1

        return purged

    def clear_all(self) -> None:
        """Clear all stored state (primarily for test isolation)."""
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()

from app.core.config import settings

login_rate_limiter = LoginRateLimiter(
    max_attempts=settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    lockout_seconds=settings.LOGIN_LOCKOUT_SECONDS,
)
