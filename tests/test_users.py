from fastapi.testclient import TestClient

from app.models.enums import UserRole
from app.models.user import User


def test_get_me_with_token(client: TestClient, requester_user: User, requester_auth_headers: dict[str, str]):
    """Test /users/me with valid bearer token returns current user profile."""
    response = client.get("/api/v1/users/me", headers=requester_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == requester_user.id
    assert data["email"] == requester_user.email
    assert data["full_name"] == requester_user.full_name
    assert data["role"] == "requester"
    assert "password" not in data
    assert "hashed_password" not in data


def test_get_me_without_token(client: TestClient):
    """Test /users/me without token returns 401 Unauthorized."""
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["message"] == "Authentication credentials were not provided"


def test_get_me_invalid_token(client: TestClient):
    """Test /users/me with invalid token returns 401 Unauthorized."""
    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer not_a_valid_token_xyz"},
    )
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["message"] == "Invalid authentication token"


def test_list_users_forbidden_for_requester(client: TestClient, requester_auth_headers: dict[str, str]):
    """Test GET /users returns 403 Forbidden when requested by a requester."""
    response = client.get("/api/v1/users", headers=requester_auth_headers)
    assert response.status_code == 403
    data = response.json()
    assert "error" in data
    assert data["error"]["message"] == "You do not have permission to access this resource"


def test_list_users_allowed_for_admin(client: TestClient, admin_auth_headers: dict[str, str]):
    """Test GET /users returns 200 and user list when requested by an admin."""
    response = client.get("/api/v1/users", headers=admin_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_patch_role_forbidden_for_requester(
    client: TestClient,
    requester_user: User,
    requester_auth_headers: dict[str, str],
):
    """Test PATCH /users/{id}/role returns 403 Forbidden when requested by a requester."""
    response = client.patch(
        f"/api/v1/users/{requester_user.id}/role",
        headers=requester_auth_headers,
        json={"role": "agent"},
    )
    assert response.status_code == 403
    data = response.json()
    assert "error" in data
    assert data["error"]["message"] == "You do not have permission to access this resource"


def test_patch_role_allowed_for_admin(
    client: TestClient,
    requester_user: User,
    admin_auth_headers: dict[str, str],
):
    """Test PATCH /users/{id}/role returns 200 and updates role when requested by an admin."""
    response = client.patch(
        f"/api/v1/users/{requester_user.id}/role",
        headers=admin_auth_headers,
        json={"role": "agent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == requester_user.id
    assert data["role"] == "agent"


def test_patch_role_nonexistent_user(client: TestClient, admin_auth_headers: dict[str, str]):
    """Test PATCH /users/{id}/role returns 404 when user id does not exist."""
    response = client.patch(
        "/api/v1/users/999999/role",
        headers=admin_auth_headers,
        json={"role": "admin"},
    )
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["message"] == "User not found"
