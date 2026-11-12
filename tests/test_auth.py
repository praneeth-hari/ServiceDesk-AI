from fastapi.testclient import TestClient


def test_register_success(client: TestClient):
    """Test successful user registration returns 201 with role 'requester' and no password exposed."""
    payload = {
        "email": "newuser@example.com",
        "full_name": "New User",
        "password": "strongpassword123",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New User"
    assert data["role"] == "requester"
    assert data["is_active"] is True
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data


def test_register_duplicate_email(client: TestClient):
    """Test registering with an existing email returns 409 Conflict with formatted error message."""
    payload = {
        "email": "duplicate@example.com",
        "full_name": "First User",
        "password": "password123",
    }
    first_res = client.post("/api/v1/auth/register", json=payload)
    assert first_res.status_code == 201

    # Second registration with identical email
    second_res = client.post("/api/v1/auth/register", json=payload)
    assert second_res.status_code == 409
    data = second_res.json()
    assert "error" in data
    assert data["error"]["message"] == "Email already registered"


def test_register_password_too_short(client: TestClient):
    """Test password shorter than 8 characters returns 422 with formatted error message."""
    payload = {
        "email": "shortpass@example.com",
        "full_name": "Short Pass User",
        "password": "1234567",  # 7 characters (min is 8)
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert "message" in data["error"]
    assert "password" in data["error"]["message"].lower()


def test_register_password_too_long(client: TestClient):
    """Test password longer than 72 bytes returns 422 with formatted error message."""
    payload = {
        "email": "longpass@example.com",
        "full_name": "Long Pass User",
        "password": "a" * 73,  # 73 characters = 73 bytes (max is 72)
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert "message" in data["error"]
    assert "password" in data["error"]["message"].lower()


def test_register_password_over_72_bytes_under_72_chars(client: TestClient):
    """Test password under 72 characters but over 72 UTF-8 bytes returns 422."""
    payload = {
        "email": "accentpass@example.com",
        "full_name": "Accent Pass User",
        "password": "é" * 40,  # 40 characters, but 80 bytes in UTF-8
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert "password" in data["error"]["message"].lower()
    assert "72 bytes" in data["error"]["message"].lower()


def test_register_invalid_email(client: TestClient):
    """Test invalid email format returns 422 with formatted error message."""
    payload = {
        "email": "not-an-email",
        "full_name": "Invalid Email User",
        "password": "validpassword123",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert "message" in data["error"]
    assert "email" in data["error"]["message"].lower()


def test_login_success(client: TestClient):
    """Test successful login returns a JWT bearer access token."""
    # Register first
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "loginuser@example.com",
            "full_name": "Login User",
            "password": "correctpassword",
        },
    )

    # Login
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "loginuser@example.com", "password": "correctpassword"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 20


def test_login_wrong_password(client: TestClient):
    """Test login with incorrect password returns 401 Unauthorized."""
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpass@example.com",
            "full_name": "Wrong Pass User",
            "password": "correctpassword",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpass@example.com", "password": "incorrectpassword"},
    )
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["message"] == "Invalid email or password"


def test_login_nonexistent_user(client: TestClient):
    """Test login with an unregistered email returns 401 Unauthorized."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "doesnotexist@example.com", "password": "anypassword"},
    )
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["message"] == "Invalid email or password"


def test_register_race_integrity_error_returns_409(client: TestClient, db_session):
    """A concurrent duplicate insert (IntegrityError at commit) yields 409, not 500."""
    from unittest.mock import patch
    from sqlalchemy.exc import IntegrityError

    payload = {"email": "race@example.com", "full_name": "Race", "password": "password123"}
    with patch.object(db_session, "commit", side_effect=IntegrityError("stmt", {}, Exception("dup"))):
        res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 409
    assert "already registered" in res.json()["error"]["message"]


def test_ticket_description_length_is_capped(client: TestClient):
    """Oversized descriptions are rejected with 422 before reaching regex/embedding work."""
    from app.schemas.common import MAX_DESCRIPTION_LENGTH

    payload = {"email": "cap@example.com", "full_name": "Cap", "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    big = "a" * (MAX_DESCRIPTION_LENGTH + 1)

    r1 = client.post("/api/v1/tickets", headers=headers, json={"title": "t", "description": big})
    assert r1.status_code == 422
    r2 = client.post("/api/v1/triage/suggest", headers=headers, json={"title": "t", "description": big})
    assert r2.status_code == 422


def test_register_is_rate_limited_per_ip(client: TestClient):
    """Exceeding the per-IP registration limit returns 429 with Retry-After."""
    from app.core.rate_limit import register_rate_limiter

    original = register_rate_limiter.max_requests
    register_rate_limiter.max_requests = 2
    try:
        for i in range(2):
            r = client.post(
                "/api/v1/auth/register",
                json={"email": f"rl{i}@example.com", "full_name": "RL", "password": "password123"},
            )
            assert r.status_code == 201
        r = client.post(
            "/api/v1/auth/register",
            json={"email": "rl3@example.com", "full_name": "RL", "password": "password123"},
        )
        assert r.status_code == 429
        assert "Retry-After" in r.headers
    finally:
        register_rate_limiter.max_requests = original


def test_triage_is_rate_limited_per_user(client: TestClient):
    """Exceeding the per-user triage limit returns 429."""
    from app.core.rate_limit import triage_rate_limiter

    client.post("/api/v1/auth/register", json={"email": "tr@example.com", "full_name": "T", "password": "password123"})
    token = client.post("/api/v1/auth/login", json={"email": "tr@example.com", "password": "password123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    body = {"title": "VPN down", "description": "Cannot connect to VPN"}

    original = triage_rate_limiter.max_requests
    triage_rate_limiter.max_requests = 1
    try:
        assert client.post("/api/v1/triage/suggest", headers=headers, json=body).status_code == 200
        assert client.post("/api/v1/triage/suggest", headers=headers, json=body).status_code == 429
    finally:
        triage_rate_limiter.max_requests = original


def test_login_unknown_email_still_verifies_a_hash(client: TestClient):
    """Unknown emails go through a bcrypt comparison (timing equalisation) and return 401."""
    from unittest.mock import patch

    with patch("app.services.users.verify_password", return_value=False) as vp:
        r = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever123"})
    assert r.status_code == 401
    assert vp.call_count == 1
