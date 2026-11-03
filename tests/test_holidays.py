from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.holiday import Holiday
from app.models.user import User


def test_create_holiday_admin(client: TestClient, admin_auth_headers: dict[str, str]):
    """Admin can create a new holiday."""
    payload = {
        "holiday_date": "2026-12-25",
        "name": "Christmas Day",
    }
    res = client.post("/api/v1/holidays", json=payload, headers=admin_auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["holiday_date"] == "2026-12-25"
    assert data["name"] == "Christmas Day"
    assert "id" in data


def test_create_holiday_duplicate_returns_409(client: TestClient, admin_auth_headers: dict[str, str]):
    """Creating a holiday on an already registered date returns 409 Conflict."""
    payload = {"holiday_date": "2026-01-26", "name": "Republic Day"}
    res1 = client.post("/api/v1/holidays", json=payload, headers=admin_auth_headers)
    assert res1.status_code == 201

    res2 = client.post("/api/v1/holidays", json=payload, headers=admin_auth_headers)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["error"]["message"]


def test_create_holiday_requester_forbidden_403(client: TestClient, requester_auth_headers: dict[str, str]):
    """Requesters cannot create holidays (403 Forbidden)."""
    res = client.post(
        "/api/v1/holidays",
        json={"holiday_date": "2026-08-15", "name": "Independence Day"},
        headers=requester_auth_headers,
    )
    assert res.status_code == 403


def test_agent_can_list_but_not_create(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    admin_auth_headers: dict[str, str],
):
    """Agents can list holidays but receive 403 Forbidden on create."""
    # Seed a holiday as admin
    client.post(
        "/api/v1/holidays",
        json={"holiday_date": "2026-10-02", "name": "Gandhi Jayanti"},
        headers=admin_auth_headers,
    )

    # Agent attempts to create -> 403
    create_res = client.post(
        "/api/v1/holidays",
        json={"holiday_date": "2026-11-01", "name": "Kannada Rajyotsava"},
        headers=agent_auth_headers,
    )
    assert create_res.status_code == 403

    # Agent lists holidays -> 200
    list_res = client.get("/api/v1/holidays", headers=agent_auth_headers)
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(h["name"] == "Gandhi Jayanti" for h in items)


def test_list_holidays_filter_by_year(client: TestClient, admin_auth_headers: dict[str, str]):
    """List holidays filtered by ?year= query parameter."""
    client.post("/api/v1/holidays", json={"holiday_date": "2025-12-31", "name": "NYE 2025"}, headers=admin_auth_headers)
    client.post("/api/v1/holidays", json={"holiday_date": "2026-01-01", "name": "New Year 2026"}, headers=admin_auth_headers)

    res_2025 = client.get("/api/v1/holidays?year=2025", headers=admin_auth_headers)
    assert res_2025.status_code == 200
    items_2025 = res_2025.json()
    assert all(h["holiday_date"].startswith("2025") for h in items_2025)

    res_2026 = client.get("/api/v1/holidays?year=2026", headers=admin_auth_headers)
    assert res_2026.status_code == 200
    items_2026 = res_2026.json()
    assert all(h["holiday_date"].startswith("2026") for h in items_2026)


def test_delete_holiday_admin_and_404(client: TestClient, admin_auth_headers: dict[str, str]):
    """Admin can delete a holiday, deleting non-existent returns 404."""
    create_res = client.post(
        "/api/v1/holidays",
        json={"holiday_date": "2026-05-01", "name": "May Day"},
        headers=admin_auth_headers,
    )
    holiday_id = create_res.json()["id"]

    del_res = client.delete(f"/api/v1/holidays/{holiday_id}", headers=admin_auth_headers)
    assert del_res.status_code == 204

    # Deleting again returns 404
    del_404 = client.delete(f"/api/v1/holidays/{holiday_id}", headers=admin_auth_headers)
    assert del_404.status_code == 404


def test_holiday_endpoints_without_token_returns_401(client: TestClient):
    """Endpoints require authentication and return 401 Unauthorized without token."""
    assert client.get("/api/v1/holidays").status_code == 401
    assert client.post("/api/v1/holidays", json={"holiday_date": "2026-01-01", "name": "NY"}).status_code == 401
    assert client.delete("/api/v1/holidays/1").status_code == 401


def test_update_holiday_success(client: TestClient, admin_auth_headers: dict[str, str]):
    """Admin can update both name and date of an existing holiday."""
    res = client.post(
        "/api/v1/holidays",
        json={"holiday_date": "2026-11-10", "name": "Initial Name"},
        headers=admin_auth_headers,
    )
    h_id = res.json()["id"]

    patch_res = client.patch(
        f"/api/v1/holidays/{h_id}",
        json={"holiday_date": "2026-11-11", "name": "Updated Name"},
        headers=admin_auth_headers,
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["holiday_date"] == "2026-11-11"
    assert data["name"] == "Updated Name"
    assert data["id"] == h_id


def test_update_holiday_name_only(client: TestClient, admin_auth_headers: dict[str, str]):
    """Admin can update only the name, leaving holiday_date unchanged."""
    res = client.post(
        "/api/v1/holidays",
        json={"holiday_date": "2026-11-12", "name": "Before Name"},
        headers=admin_auth_headers,
    )
    h_id = res.json()["id"]

    patch_res = client.patch(
        f"/api/v1/holidays/{h_id}",
        json={"name": "After Name"},
        headers=admin_auth_headers,
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["holiday_date"] == "2026-11-12"
    assert data["name"] == "After Name"


def test_update_holiday_date_only(client: TestClient, admin_auth_headers: dict[str, str]):
    """Admin can update only the date, leaving name unchanged."""
    res = client.post(
        "/api/v1/holidays",
        json={"holiday_date": "2026-11-13", "name": "Constant Name"},
        headers=admin_auth_headers,
    )
    h_id = res.json()["id"]

    patch_res = client.patch(
        f"/api/v1/holidays/{h_id}",
        json={"holiday_date": "2026-11-14"},
        headers=admin_auth_headers,
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["holiday_date"] == "2026-11-14"
    assert data["name"] == "Constant Name"


def test_update_holiday_same_date_noop(client: TestClient, admin_auth_headers: dict[str, str]):
    """Updating a holiday with its current date must succeed without 409 conflict."""
    res = client.post(
        "/api/v1/holidays",
        json={"holiday_date": "2026-11-15", "name": "Same Date Test"},
        headers=admin_auth_headers,
    )
    h_id = res.json()["id"]

    patch_res = client.patch(
        f"/api/v1/holidays/{h_id}",
        json={"holiday_date": "2026-11-15", "name": "Same Date Test Modified"},
        headers=admin_auth_headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Same Date Test Modified"


def test_update_holiday_404_not_found(client: TestClient, admin_auth_headers: dict[str, str]):
    """Updating a non-existent holiday ID returns 404 Not Found."""
    patch_res = client.patch(
        "/api/v1/holidays/99999",
        json={"name": "Ghost"},
        headers=admin_auth_headers,
    )
    assert patch_res.status_code == 404
    assert patch_res.json()["error"]["message"] == "Holiday not found"


def test_update_holiday_409_conflict(client: TestClient, admin_auth_headers: dict[str, str]):
    """Updating date to one already taken by a different holiday returns 409 Conflict."""
    client.post(
        "/api/v1/holidays",
        json={"holiday_date": "2026-11-16", "name": "Existing Holiday"},
        headers=admin_auth_headers,
    )
    h2 = client.post(
        "/api/v1/holidays",
        json={"holiday_date": "2026-11-17", "name": "Second Holiday"},
        headers=admin_auth_headers,
    )
    h2_id = h2.json()["id"]

    # Try updating h2's date to h1's date
    patch_res = client.patch(
        f"/api/v1/holidays/{h2_id}",
        json={"holiday_date": "2026-11-16"},
        headers=admin_auth_headers,
    )
    assert patch_res.status_code == 409
    assert "already exists" in patch_res.json()["error"]["message"]


def test_update_holiday_403_forbidden(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
    requester_auth_headers: dict[str, str],
):
    """Agents and requesters cannot update holidays (403 Forbidden)."""
    res = client.post(
        "/api/v1/holidays",
        json={"holiday_date": "2026-11-18", "name": "Restricted Holiday"},
        headers=admin_auth_headers,
    )
    h_id = res.json()["id"]

    # Agent -> 403
    agent_res = client.patch(
        f"/api/v1/holidays/{h_id}",
        json={"name": "Agent Edit"},
        headers=agent_auth_headers,
    )
    assert agent_res.status_code == 403

    # Requester -> 403
    req_res = client.patch(
        f"/api/v1/holidays/{h_id}",
        json={"name": "Req Edit"},
        headers=requester_auth_headers,
    )
    assert req_res.status_code == 403


def test_update_holiday_422_validation(client: TestClient, admin_auth_headers: dict[str, str]):
    """Invalid payload (empty name or malformed date) returns 422 Unprocessable Entity."""
    res = client.post(
        "/api/v1/holidays",
        json={"holiday_date": "2026-11-19", "name": "Validation Test"},
        headers=admin_auth_headers,
    )
    h_id = res.json()["id"]

    # Empty name (min_length=1)
    res_empty_name = client.patch(
        f"/api/v1/holidays/{h_id}",
        json={"name": ""},
        headers=admin_auth_headers,
    )
    assert res_empty_name.status_code == 422

    # Malformed date
    res_bad_date = client.patch(
        f"/api/v1/holidays/{h_id}",
        json={"holiday_date": "invalid-date"},
        headers=admin_auth_headers,
    )
    assert res_bad_date.status_code == 422
