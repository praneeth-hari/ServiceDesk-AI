from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import LoginRateLimiter, login_rate_limiter, mask_email
from app.models.enums import UserRole
from app.models.user import User


# ===========================================================================
# 1. Unit Tests for LoginRateLimiter (with fake clock)
# ===========================================================================

class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.current_time = start

    def __call__(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


def test_rate_limiter_mask_email():
    """Verify email masking for logs does not expose full email or passwords."""
    assert mask_email("a@b.com") == "*@b.com"
    assert mask_email("ab@b.com") == "a***@b.com"
    assert mask_email("ravi@example.com") == "ra***i@example.com"
    assert mask_email("admin@example.com") == "ad***n@example.com"
    assert mask_email("nopunctuation") == "no***"
    assert mask_email("x") == "***"


def test_rate_limiter_5_failures_lock():
    """Verify 5 failures lock the key, and remaining lockout time is reported."""
    clock = FakeClock(1000.0)
    limiter = LoginRateLimiter(
        max_attempts=5,
        window_seconds=300,
        lockout_seconds=300,
        clock=clock,
    )

    # 4 failures: not locked
    for i in range(4):
        clock.advance(1.0)
        just_locked = limiter.record_failure("user@example.com", "1.2.3.4")
        assert not just_locked
        locked, remaining = limiter.is_locked("user@example.com", "1.2.3.4")
        assert not locked
        assert remaining == 0

    # 5th failure locks the key
    clock.advance(1.0)
    just_locked = limiter.record_failure("user@example.com", "1.2.3.4")
    assert just_locked

    locked, remaining = limiter.is_locked("user@example.com", "1.2.3.4")
    assert locked
    assert 295 <= remaining <= 300


def test_rate_limiter_window_expiry_unlocks():
    """Verify sliding window expiry drops old failures and does not lock."""
    clock = FakeClock(1000.0)
    limiter = LoginRateLimiter(
        max_attempts=5,
        window_seconds=300,
        lockout_seconds=300,
        clock=clock,
    )

    # 4 failures at t=1000
    for _ in range(4):
        limiter.record_failure("user@example.com", "1.2.3.4")

    # Advance clock past the 300s window
    clock.advance(301.0)

    # Old attempts expired, so another failure brings count to 1 (not 5)
    limiter.record_failure("user@example.com", "1.2.3.4")
    locked, _ = limiter.is_locked("user@example.com", "1.2.3.4")
    assert not locked

    # If it was locked, advancing clock past lockout_seconds unlocks it
    for _ in range(4):
        limiter.record_failure("user@example.com", "1.2.3.4")
    locked, _ = limiter.is_locked("user@example.com", "1.2.3.4")
    assert locked

    clock.advance(301.0)
    locked, _ = limiter.is_locked("user@example.com", "1.2.3.4")
    assert not locked


def test_rate_limiter_success_resets():
    """Verify successful login resets failure counter and lockout."""
    clock = FakeClock(1000.0)
    limiter = LoginRateLimiter(
        max_attempts=5,
        window_seconds=300,
        lockout_seconds=300,
        clock=clock,
    )

    for _ in range(4):
        limiter.record_failure("user@example.com", "1.2.3.4")

    # Reset
    limiter.reset("user@example.com", "1.2.3.4")

    # Adding 1 more failure should not lock (counter was cleared)
    limiter.record_failure("user@example.com", "1.2.3.4")
    locked, _ = limiter.is_locked("user@example.com", "1.2.3.4")
    assert not locked


def test_rate_limiter_independence_email_and_ip():
    """Verify different email addresses and different IPs are tracked independently."""
    clock = FakeClock(1000.0)
    limiter = LoginRateLimiter(
        max_attempts=5,
        window_seconds=300,
        lockout_seconds=300,
        clock=clock,
    )

    # Lock user1@example.com on IP1
    for _ in range(5):
        limiter.record_failure("user1@example.com", "10.0.0.1")

    assert limiter.is_locked("user1@example.com", "10.0.0.1")[0]

    # Different email on same IP is NOT locked
    assert not limiter.is_locked("user2@example.com", "10.0.0.1")[0]

    # Same email on different IP is NOT locked
    assert not limiter.is_locked("user1@example.com", "10.0.0.2")[0]

    # Email normalization (case and whitespace) matches the locked key
    assert limiter.is_locked("  USER1@EXAMPLE.COM ", "10.0.0.1")[0]


def test_rate_limiter_stale_key_purge():
    """Verify purge_stale() clears expired keys from memory."""
    clock = FakeClock(1000.0)
    limiter = LoginRateLimiter(
        max_attempts=5,
        window_seconds=300,
        lockout_seconds=300,
        clock=clock,
    )

    # Key 1 has 1 failure
    limiter.record_failure("stale1@example.com", "1.1.1.1")
    # Key 2 gets locked
    for _ in range(5):
        limiter.record_failure("stale2@example.com", "2.2.2.2")

    # Advance clock past window and lockout
    clock.advance(305.0)

    purged = limiter.purge_stale()
    assert purged >= 2
    assert len(limiter._failures) == 0
    assert len(limiter._locked_until) == 0


# ===========================================================================
# 2. Endpoint Tests: Demo Accounts & Demo Login
# ===========================================================================

def test_demo_accounts_disabled(client: TestClient):
    """When DEMO_MODE is False, demo-accounts returns enabled=False and empty list."""
    with patch.object(settings, "DEMO_MODE", False):
        res = client.get("/api/v1/auth/demo-accounts")
        assert res.status_code == 200
        data = res.json()
        assert data["enabled"] is False
        assert data["accounts"] == []


def test_demo_login_disabled_returns_404(client: TestClient):
    """When DEMO_MODE is False, POST demo-login returns 404 Not Found."""
    with patch.object(settings, "DEMO_MODE", False):
        res = client.post("/api/v1/auth/demo-login", json={"role": "agent"})
        assert res.status_code == 404
        assert "disabled" in res.json()["error"]["message"].lower()


def test_demo_accounts_enabled_lists_roles(client: TestClient):
    """
    When DEMO_MODE is True, demo-accounts lists requester, agent, and admin.
    Never exposes emails or passwords.
    """
    with patch.object(settings, "DEMO_MODE", True):
        res = client.get("/api/v1/auth/demo-accounts")
        assert res.status_code == 200
        data = res.json()
        assert data["enabled"] is True
        accounts = data["accounts"]
        assert len(accounts) == 3

        roles = [a["role"] for a in accounts]
        assert roles == ["requester", "agent", "admin"]

        for acc in accounts:
            assert "name" in acc and len(acc["name"]) > 0
            assert "description" in acc and len(acc["description"]) > 0
            # Strict security checks: no credentials leaked
            assert "email" not in acc
            assert "password" not in acc
            assert "@" not in str(acc)


def test_demo_login_success_for_all_roles(
    client: TestClient,
    requester_user: User,
    agent_user: User,
    admin_user: User,
):
    """
    When DEMO_MODE is True, demo-login for requester, agent, and admin returns
    valid JWT tokens, and /users/me reports the matching role.
    """
    with patch.object(settings, "DEMO_MODE", True):
        for role_name in ["requester", "agent", "admin"]:
            login_res = client.post("/api/v1/auth/demo-login", json={"role": role_name})
            assert login_res.status_code == 200
            token_data = login_res.json()
            assert "access_token" in token_data
            assert token_data["token_type"] == "bearer"

            # Verify token works on /users/me and matches expected role
            headers = {"Authorization": f"Bearer {token_data['access_token']}"}
            me_res = client.get("/api/v1/users/me", headers=headers)
            assert me_res.status_code == 200
            user_data = me_res.json()
            assert user_data["role"] == role_name


def test_demo_login_invalid_role(client: TestClient):
    """Invalid role returns 422 Unprocessable Entity."""
    with patch.object(settings, "DEMO_MODE", True):
        res = client.post("/api/v1/auth/demo-login", json={"role": "superadmin"})
        assert res.status_code == 422


def test_demo_login_missing_seeded_user(client: TestClient, db_session: Session):
    """
    If the seeded user does not exist in the database, return 404 suggesting seed_demo.
    """
    with patch.object(settings, "DEMO_MODE", True):
        # We did not seed requester_user in this test, so requester won't be in DB
        res = client.post("/api/v1/auth/demo-login", json={"role": "requester"})
        assert res.status_code == 404
        msg = res.json()["error"]["message"]
        assert "seed_demo" in msg


# ===========================================================================
# 3. Endpoint Tests: Rate Limiting & Lockout
# ===========================================================================

def test_login_rate_limiting_lockout_and_demo_bypass(
    client: TestClient,
    agent_user: User,
):
    """
    Test endpoint-level password lockout:
    1. 5 failed logins return 401.
    2. 6th attempt returns 429 with Retry-After header and detail + retry_after_seconds.
    3. Even correct password returns 429 while locked.
    4. Demo-login remains usable while password login is locked.
    5. Unknown email counts identically to wrong password (no user enumeration).
    """
    login_rate_limiter.clear_all()

    # Attempts 1 to 5 with wrong password
    for i in range(5):
        res = client.post(
            "/api/v1/auth/login",
            json={"email": agent_user.email, "password": "WrongPassword!"},
        )
        assert res.status_code == 401
        assert res.json()["error"]["message"] == "Invalid email or password"

    # 6th attempt: locked out! Returns 429 with Retry-After
    res_locked = client.post(
        "/api/v1/auth/login",
        json={"email": agent_user.email, "password": "WrongPassword!"},
    )
    assert res_locked.status_code == 429
    assert "Retry-After" in res_locked.headers
    retry_after = int(res_locked.headers["Retry-After"])
    assert retry_after > 0

    data = res_locked.json()
    assert "retry_after_seconds" in data
    assert data["retry_after_seconds"] == retry_after
    assert "detail" in data

    # Attempt with CORRECT password during lockout: still blocked with 429!
    res_correct_during_lockout = client.post(
        "/api/v1/auth/login",
        json={"email": agent_user.email, "password": "AgentPassword123!"},
    )
    assert res_correct_during_lockout.status_code == 429
    assert "Retry-After" in res_correct_during_lockout.headers

    # Demo-login is NOT subject to password lockout
    with patch.object(settings, "DEMO_MODE", True):
        demo_res = client.post("/api/v1/auth/demo-login", json={"role": "agent"})
        assert demo_res.status_code == 200
        assert "access_token" in demo_res.json()

    # Unknown email counts identically and doesn't reveal user existence
    login_rate_limiter.clear_all()
    unknown_email = "nonexistent_random_user_123@example.com"
    for _ in range(5):
        res = client.post(
            "/api/v1/auth/login",
            json={"email": unknown_email, "password": "AnyPassword!"},
        )
        assert res.status_code == 401
        assert res.json()["error"]["message"] == "Invalid email or password"

    res_unknown_locked = client.post(
        "/api/v1/auth/login",
        json={"email": unknown_email, "password": "AnyPassword!"},
    )
    assert res_unknown_locked.status_code == 429

    login_rate_limiter.clear_all()


# ===========================================================================
# 4. Inactive Account Authentication & Rate Limiting
# ===========================================================================

def test_login_inactive_user_wrong_password_returns_generic_error_and_counts_toward_rate_limit(
    client: TestClient,
    db_session: Session,
):
    """
    When an account has is_active=False, a wrong password returns the generic
    'Invalid email or password' (no leakage of account existence or active status),
    and counts toward the rate limit.
    """
    from app.core.security import hash_password
    login_rate_limiter.clear_all()

    inactive_user = User(
        email="inactive_wrong@example.com",
        full_name="Inactive User",
        hashed_password=hash_password("RealSecret123!"),
        role=UserRole.REQUESTER,
        is_active=False,
    )
    db_session.add(inactive_user)
    db_session.commit()

    # Wrong password attempt
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "inactive_wrong@example.com", "password": "WrongPassword!"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["message"] == "Invalid email or password"

    # Verify failure counter increased (1 failure tracked in rate limiter)
    assert ("inactive_wrong@example.com", "testclient") in login_rate_limiter._failures or (
        "inactive_wrong@example.com", "127.0.0.1"
    ) in login_rate_limiter._failures
    login_rate_limiter.clear_all()


def test_login_inactive_user_correct_password_returns_inactive_error_and_counts_toward_rate_limit(
    client: TestClient,
    db_session: Session,
):
    """
    When an account has is_active=False, the 'User account is inactive' message
    is returned ONLY AFTER password verification succeeds. Failed attempts also
    count toward the rate limit.
    """
    from app.core.security import hash_password
    login_rate_limiter.clear_all()

    inactive_user = User(
        email="inactive_correct@example.com",
        full_name="Inactive User",
        hashed_password=hash_password("RealSecret123!"),
        role=UserRole.REQUESTER,
        is_active=False,
    )
    db_session.add(inactive_user)
    db_session.commit()

    # Correct password attempt
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "inactive_correct@example.com", "password": "RealSecret123!"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["message"] == "User account is inactive"

    # Verify failure counter increased
    assert ("inactive_correct@example.com", "testclient") in login_rate_limiter._failures or (
        "inactive_correct@example.com", "127.0.0.1"
    ) in login_rate_limiter._failures
    login_rate_limiter.clear_all()


def test_login_inactive_user_lockout_after_5_failures(
    client: TestClient,
    db_session: Session,
):
    """
    Failed attempts on inactive accounts count toward the rate limit and trigger lockout.
    """
    from app.core.security import hash_password
    login_rate_limiter.clear_all()

    inactive_user = User(
        email="inactive_lockout@example.com",
        full_name="Inactive User",
        hashed_password=hash_password("RealSecret123!"),
        role=UserRole.REQUESTER,
        is_active=False,
    )
    db_session.add(inactive_user)
    db_session.commit()

    # 5 failed attempts (mix of wrong and right passwords)
    for i in range(5):
        pw = "WrongPass!" if i % 2 == 0 else "RealSecret123!"
        res = client.post(
            "/api/v1/auth/login",
            json={"email": "inactive_lockout@example.com", "password": pw},
        )
        assert res.status_code == 401

    # 6th attempt: locked out with 429
    res_locked = client.post(
        "/api/v1/auth/login",
        json={"email": "inactive_lockout@example.com", "password": "RealSecret123!"},
    )
    assert res_locked.status_code == 429
    assert "Retry-After" in res_locked.headers
    login_rate_limiter.clear_all()


# ===========================================================================
# 5. Startup Warning on DEMO_MODE
# ===========================================================================

def test_startup_warning_when_demo_mode_enabled(caplog):
    """When DEMO_MODE is True, lifespan logs a clear SECURITY WARNING at startup."""
    import logging
    from app.main import app

    with patch.object(settings, "DEMO_MODE", True):
        with caplog.at_level(logging.WARNING, logger="helpdesk_api"):
            with TestClient(app):
                pass
        warnings = [rec.message for rec in caplog.records if "SECURITY WARNING: DEMO_MODE is enabled" in rec.message]
        assert len(warnings) >= 1
        assert "passwordless sign-in" in warnings[0]
        assert "never be enabled on a real deployment" in warnings[0]


def test_startup_no_warning_when_demo_mode_disabled(caplog):
    """When DEMO_MODE is False, no DEMO_MODE startup warning is logged."""
    import logging
    from app.main import app

    with patch.object(settings, "DEMO_MODE", False):
        with caplog.at_level(logging.WARNING, logger="helpdesk_api"):
            with TestClient(app):
                pass
        warnings = [rec.message for rec in caplog.records if "DEMO_MODE is enabled" in rec.message]
        assert len(warnings) == 0
