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
