import logging
import re
import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.logging import SANE_REQUEST_ID_REGEX, get_sane_request_id, request_id_ctx


def test_get_sane_request_id():
    """Test validation of incoming request IDs."""
    # Sane IDs: alphanumeric and dashes, <= 64 chars
    assert get_sane_request_id("my-trace-id-123") == "my-trace-id-123"
    assert get_sane_request_id("1234567890") == "1234567890"

    # None or empty generates valid UUID
    val_empty = get_sane_request_id(None)
    assert uuid.UUID(val_empty)

    # Insane IDs: invalid chars (e.g., spaces, @, $, semicolon)
    val_invalid = get_sane_request_id("bad id with spaces")
    assert uuid.UUID(val_invalid)
    assert val_invalid != "bad id with spaces"

    val_special = get_sane_request_id("id_with_underscore;DROP TABLE")
    assert uuid.UUID(val_special)

    # Insane ID: longer than 64 characters
    val_too_long = get_sane_request_id("a" * 65)
    assert uuid.UUID(val_too_long)
    assert val_too_long != "a" * 65


def test_request_id_in_response_headers(client: TestClient):
    """Test that every response includes an X-Request-ID header."""
    # 1. No header sent -> server generates UUID
    res1 = client.get("/api/v1/health")
    assert res1.status_code == 200
    req_id1 = res1.headers.get("X-Request-ID")
    assert req_id1 is not None
    assert uuid.UUID(req_id1)

    # 2. Sane custom header sent -> server returns identical header
    custom_id = "trace-abc-12345"
    res2 = client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert res2.status_code == 200
    assert res2.headers.get("X-Request-ID") == custom_id

    # 3. Insane custom header sent -> server generates new UUID instead of passing it through
    res3 = client.get("/api/v1/health", headers={"X-Request-ID": "injection;alert(1)"})
    assert res3.status_code == 200
    req_id3 = res3.headers.get("X-Request-ID")
    assert req_id3 != "injection;alert(1)"
    assert uuid.UUID(req_id3)


def test_logging_middleware_logs_request_line(client: TestClient, caplog):
    """Test that the middleware logs one line containing request_id, method, path, status, and duration."""
    with caplog.at_level(logging.INFO, logger="helpdesk_api"):
        res = client.get("/api/v1/health", headers={"X-Request-ID": "req-track-777"})
        assert res.status_code == 200

    # Find the middleware request log record
    req_records = [
        rec for rec in caplog.records
        if "request_id=req-track-777" in rec.message and "path=/api/v1/health" in rec.message
    ]
    assert len(req_records) == 1
    record = req_records[0]
    assert "method=GET" in record.message
    assert "status_code=200" in record.message
    assert "duration_ms=" in record.message
    assert getattr(record, "request_id", None) == "req-track-777"


def test_never_log_passwords_tokens_or_auth_headers(client: TestClient, caplog):
    """
    Test that passwords, tokens, Authorization headers, and request bodies
    are NEVER logged anywhere during user registration, login, and authenticated requests.
    """
    secret_pass = "P@ssw0rd999_SuperSecretVal"
    user_email = "auditloguser@example.com"

    with caplog.at_level(logging.DEBUG, logger="helpdesk_api"):
        # 1. Register user
        reg_res = client.post(
            "/api/v1/auth/register",
            json={"email": user_email, "full_name": "Audit User", "password": secret_pass},
        )
        assert reg_res.status_code == 201

        # 2. Login user
        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": user_email, "password": secret_pass},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        # 3. Access protected route with Bearer token
        me_res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res.status_code == 200

    all_log_text = caplog.text

    # Assert password NEVER appears in any log record
    assert secret_pass not in all_log_text

    # Assert JWT token NEVER appears in any log record
    assert token not in all_log_text

    # Assert Authorization header value NEVER appears in any log record
    assert f"Bearer {token}" not in all_log_text
    assert "Bearer " not in all_log_text

    # Assert request bodies are NOT logged
    assert f'"password": "{secret_pass}"' not in all_log_text
