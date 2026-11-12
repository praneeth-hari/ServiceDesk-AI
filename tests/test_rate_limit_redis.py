"""
Tests for the Redis-backed rate limiters, using a controllable clock.

They use fakeredis by default. Set TEST_REDIS_URL (for example redis://127.0.0.1:6379/15) to run
them against a real Redis server instead; the database is flushed before and after each test.
"""
import os
from unittest.mock import MagicMock

from fastapi import HTTPException
import fakeredis
import pytest

from app.core.rate_limit_redis import RedisLoginRateLimiter, RedisRequestRateLimiter


class Clock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def redis_client():
    url = os.getenv("TEST_REDIS_URL")
    if url:
        import redis

        client = redis.Redis.from_url(url, decode_responses=True)
        client.flushdb()
        yield client
        client.flushdb()
    else:
        yield fakeredis.FakeRedis(decode_responses=True)


# ---- request limiter -------------------------------------------------------

def test_request_limiter_blocks_after_max_and_sets_retry_after(redis_client):
    clock = Clock()
    limiter = RedisRequestRateLimiter(redis_client, "t", max_requests=3, window_seconds=60, clock=clock)
    for _ in range(3):
        limiter.check("ip1")
        clock.now += 1
    with pytest.raises(HTTPException) as exc:
        limiter.check("ip1")
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "57"  # oldest request was 3s ago, window is 60s
    assert exc.value.detail["retry_after_seconds"] == 57


def test_request_limiter_window_slides_and_keys_are_independent(redis_client):
    clock = Clock()
    limiter = RedisRequestRateLimiter(redis_client, "t", max_requests=2, window_seconds=60, clock=clock)
    limiter.check("a")
    limiter.check("a")
    limiter.check("b")  # another key is unaffected
    with pytest.raises(HTTPException):
        limiter.check("a")
    clock.now += 61  # window has passed
    limiter.check("a")


def test_blocked_request_does_not_extend_the_block(redis_client):
    clock = Clock()
    limiter = RedisRequestRateLimiter(redis_client, "t", max_requests=1, window_seconds=60, clock=clock)
    limiter.check("a")
    for _ in range(5):
        clock.now += 5
        with pytest.raises(HTTPException):
            limiter.check("a")
    clock.now += 40  # 65s after the only counted request
    limiter.check("a")


def test_request_limiter_zero_disables(redis_client):
    limiter = RedisRequestRateLimiter(redis_client, "t", max_requests=0, window_seconds=60)
    for _ in range(50):
        limiter.check("a")


def test_state_is_shared_between_instances(redis_client):
    """Two limiter objects on one Redis behave like two workers sharing one limit."""
    clock = Clock()
    worker1 = RedisRequestRateLimiter(redis_client, "t", max_requests=2, window_seconds=60, clock=clock)
    worker2 = RedisRequestRateLimiter(redis_client, "t", max_requests=2, window_seconds=60, clock=clock)
    worker1.check("a")
    worker2.check("a")
    with pytest.raises(HTTPException):
        worker1.check("a")


def test_request_limiter_fails_open_when_redis_is_down():
    broken = MagicMock()
    broken.pipeline.side_effect = ConnectionError("redis down")
    limiter = RedisRequestRateLimiter(broken, "t", max_requests=1, window_seconds=60)
    limiter.check("a")
    limiter.check("a")  # no exception: the request is allowed


# ---- login limiter ---------------------------------------------------------

def make_login(redis_client, clock):
    return RedisLoginRateLimiter(
        redis_client, max_attempts=3, window_seconds=60, lockout_seconds=120, clock=clock
    )


def test_login_locks_after_max_failures(redis_client):
    clock = Clock()
    limiter = make_login(redis_client, clock)
    assert limiter.record_failure("User@Example.com", "1.1.1.1") is False
    assert limiter.record_failure("user@example.com", "1.1.1.1") is False
    assert limiter.record_failure("user@example.com ", "1.1.1.1") is True  # third failure locks
    locked, retry = limiter.is_locked("USER@example.com", "1.1.1.1")
    assert locked and retry == 120
    with pytest.raises(HTTPException) as exc:
        limiter.check_and_raise_if_locked("user@example.com", "1.1.1.1")
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "120"


def test_login_lock_expires(redis_client):
    clock = Clock()
    limiter = make_login(redis_client, clock)
    for _ in range(3):
        limiter.record_failure("a@x.com", "ip")
    assert limiter.is_locked("a@x.com", "ip")[0]
    clock.now += 121
    assert limiter.is_locked("a@x.com", "ip") == (False, 0)
    # After the lock ends the key starts fresh
    assert limiter.record_failure("a@x.com", "ip") is False


def test_login_failures_outside_window_do_not_count(redis_client):
    clock = Clock()
    limiter = make_login(redis_client, clock)
    limiter.record_failure("a@x.com", "ip")
    limiter.record_failure("a@x.com", "ip")
    clock.now += 61
    assert limiter.record_failure("a@x.com", "ip") is False
    assert limiter.is_locked("a@x.com", "ip") == (False, 0)


def test_login_success_resets_and_keys_are_independent(redis_client):
    clock = Clock()
    limiter = make_login(redis_client, clock)
    for _ in range(3):
        limiter.record_failure("a@x.com", "ip1")
    assert limiter.is_locked("a@x.com", "ip1")[0]
    assert limiter.is_locked("a@x.com", "ip2") == (False, 0)  # same email, other IP
    assert limiter.is_locked("b@x.com", "ip1") == (False, 0)  # other email, same IP
    limiter.reset("a@x.com", "ip1")
    assert limiter.is_locked("a@x.com", "ip1") == (False, 0)


def test_login_lock_is_shared_between_instances(redis_client):
    clock = Clock()
    worker1 = make_login(redis_client, clock)
    worker2 = make_login(redis_client, clock)
    for _ in range(3):
        worker1.record_failure("a@x.com", "ip")
    assert worker2.is_locked("a@x.com", "ip")[0]


def test_login_limiter_fails_open_when_redis_is_down():
    broken = MagicMock()
    broken.get.side_effect = ConnectionError("redis down")
    broken.pipeline.side_effect = ConnectionError("redis down")
    limiter = RedisLoginRateLimiter(broken)
    assert limiter.is_locked("a@x.com", "ip") == (False, 0)
    assert limiter.record_failure("a@x.com", "ip") is False
    limiter.check_and_raise_if_locked("a@x.com", "ip")
    limiter.reset("a@x.com", "ip")


def test_factory_uses_redis_limiters_when_redis_url_is_set(monkeypatch, redis_client):
    from app.core import rate_limit
    from app.core.config import settings

    monkeypatch.setattr(settings, "REDIS_URL", "redis://example:6379/0")
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **k: redis_client)
    login, register, triage = rate_limit._build_limiters()
    assert isinstance(login, RedisLoginRateLimiter)
    assert isinstance(register, RedisRequestRateLimiter)
    assert triage.max_requests == settings.TRIAGE_RATE_LIMIT_MAX_REQUESTS


def test_factory_uses_in_memory_limiters_without_redis_url(monkeypatch):
    from app.core import rate_limit
    from app.core.config import settings

    monkeypatch.setattr(settings, "REDIS_URL", None)
    login, register, triage = rate_limit._build_limiters()
    assert isinstance(login, rate_limit.LoginRateLimiter)
    assert isinstance(register, rate_limit.RequestRateLimiter)


def test_redis_url_scheme_is_validated():
    from app.core.config import Settings

    with pytest.raises(ValueError, match="REDIS_URL"):
        Settings(_env_file=None, REDIS_URL="http://example.com")
