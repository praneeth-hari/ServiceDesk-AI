import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.user import User
from tests.conftest import test_engine


def test_create_ticket_populates_requester_name_and_null_assignee(
    client: TestClient,
    requester_user: User,
    requester_auth_headers: dict[str, str],
):
    """Creating a ticket populates requester_name and sets assignee_name to None."""
    payload = {
        "title": "Network connectivity problem",
        "description": "Ethernet port at desk 4B is inactive.",
        "priority": "medium",
        "category": "network",
    }
    response = client.post("/api/v1/tickets", json=payload, headers=requester_auth_headers)
    assert response.status_code == 201
    data = response.json()

    assert data["requester_id"] == requester_user.id
    assert data["requester_name"] == requester_user.full_name
    assert data["assignee_id"] is None
    assert data["assignee_name"] is None


def test_get_ticket_unassigned_and_assigned(
    client: TestClient,
    requester_user: User,
    requester_auth_headers: dict[str, str],
    agent_user: User,
    agent_auth_headers: dict[str, str],
):
    """GET /tickets/{id} returns proper names for unassigned and assigned tickets."""
    create_res = client.post(
        "/api/v1/tickets",
        json={"title": "Test names get", "description": "Desc"},
        headers=requester_auth_headers,
    )
    assert create_res.status_code == 201
    ticket_id = create_res.json()["id"]

    # 1. Unassigned ticket
    get_res = client.get(f"/api/v1/tickets/{ticket_id}", headers=requester_auth_headers)
    assert get_res.status_code == 200
    data_unassigned = get_res.json()
    assert data_unassigned["requester_name"] == requester_user.full_name
    assert data_unassigned["assignee_name"] is None

    # 2. Assign ticket to agent
    assign_res = client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        json={"assignee_id": agent_user.id},
        headers=agent_auth_headers,
    )
    assert assign_res.status_code == 200

    # 3. Assigned ticket
    get_res_assigned = client.get(f"/api/v1/tickets/{ticket_id}", headers=requester_auth_headers)
    assert get_res_assigned.status_code == 200
    data_assigned = get_res_assigned.json()
    assert data_assigned["requester_name"] == requester_user.full_name
    assert data_assigned["assignee_name"] == agent_user.full_name


def test_assign_ticket_response_populates_both_names(
    client: TestClient,
    requester_user: User,
    requester_auth_headers: dict[str, str],
    agent_user: User,
    agent_auth_headers: dict[str, str],
):
    """PATCH /tickets/{id}/assign immediately returns both requester_name and assignee_name."""
    create_res = client.post(
        "/api/v1/tickets",
        json={"title": "Needs assignment", "description": "Desc"},
        headers=requester_auth_headers,
    )
    ticket_id = create_res.json()["id"]

    assign_res = client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        json={"assignee_id": agent_user.id},
        headers=agent_auth_headers,
    )
    assert assign_res.status_code == 200
    data = assign_res.json()
    assert data["requester_name"] == requester_user.full_name
    assert data["assignee_name"] == agent_user.full_name
    assert data["assignee_id"] == agent_user.id


def test_update_ticket_response_populates_names(
    client: TestClient,
    requester_user: User,
    requester_auth_headers: dict[str, str],
    agent_user: User,
    agent_auth_headers: dict[str, str],
):
    """PATCH /tickets/{id} returns populated requester_name and assignee_name."""
    create_res = client.post(
        "/api/v1/tickets",
        json={"title": "Original Title", "description": "Original Desc"},
        headers=requester_auth_headers,
    )
    ticket_id = create_res.json()["id"]

    # Assign to agent first
    client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        json={"assignee_id": agent_user.id},
        headers=agent_auth_headers,
    )

    # Update category by agent
    update_res = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"category": "hardware"},
        headers=agent_auth_headers,
    )
    assert update_res.status_code == 200
    data = update_res.json()
    assert data["category"] == "hardware"
    assert data["requester_name"] == requester_user.full_name
    assert data["assignee_name"] == agent_user.full_name


def test_list_tickets_populates_names_across_items(
    client: TestClient,
    requester_user: User,
    requester_auth_headers: dict[str, str],
    agent_user: User,
    agent_auth_headers: dict[str, str],
):
    """GET /tickets returns populated requester_name and assignee_name for all items."""
    # Create an unassigned ticket
    client.post(
        "/api/v1/tickets",
        json={"title": "Unassigned Ticket", "description": "Desc 1"},
        headers=requester_auth_headers,
    )
    # Create an assigned ticket
    t2_res = client.post(
        "/api/v1/tickets",
        json={"title": "Assigned Ticket", "description": "Desc 2"},
        headers=requester_auth_headers,
    )
    t2_id = t2_res.json()["id"]
    client.patch(
        f"/api/v1/tickets/{t2_id}/assign",
        json={"assignee_id": agent_user.id},
        headers=agent_auth_headers,
    )

    list_res = client.get("/api/v1/tickets", headers=agent_auth_headers)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) >= 2

    for item in items:
        assert "requester_name" in item
        assert "assignee_name" in item
        assert item["requester_name"] is not None
        if item["assignee_id"] is not None:
            assert item["assignee_name"] is not None
        else:
            assert item["assignee_name"] is None


def test_no_sensitive_fields_leaked_in_ticket_response(
    client: TestClient,
    requester_user: User,
    requester_auth_headers: dict[str, str],
    agent_user: User,
    agent_auth_headers: dict[str, str],
):
    """Verify that neither email, password hash, nor raw user dicts leak in ticket responses."""
    create_res = client.post(
        "/api/v1/tickets",
        json={"title": "Privacy check ticket", "description": "Confidential info"},
        headers=requester_auth_headers,
    )
    ticket_id = create_res.json()["id"]

    client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        json={"assignee_id": agent_user.id},
        headers=agent_auth_headers,
    )

    get_res = client.get(f"/api/v1/tickets/{ticket_id}", headers=agent_auth_headers)
    assert get_res.status_code == 200
    data = get_res.json()

    # Disallowed keys
    disallowed_keys = {
        "email",
        "hashed_password",
        "password",
        "requester_email",
        "assignee_email",
        "user",
        "requester",
        "assignee",
    }
    for key in disallowed_keys:
        assert key not in data, f"Sensitive key '{key}' found in ticket response"

    # Raw response body text search
    response_text = get_res.text
    assert requester_user.email not in response_text
    assert agent_user.email not in response_text
    assert requester_user.hashed_password not in response_text
    assert agent_user.hashed_password not in response_text


def test_list_tickets_query_count_does_not_grow_with_ticket_count(
    client: TestClient,
    requester_user: User,
    requester_auth_headers: dict[str, str],
    agent_user: User,
    agent_auth_headers: dict[str, str],
):
    """
    Test that joinedload prevents N+1 queries.
    Fetching 1 ticket vs fetching 5 tickets executes the exact same number of database queries
    (1 count query + 1 select query with joins = 2 queries total).
    """
    # Create 5 tickets
    for i in range(5):
        r = client.post(
            "/api/v1/tickets",
            json={"title": f"N+1 Test Ticket {i}", "description": f"Desc {i}"},
            headers=requester_auth_headers,
        )
        t_id = r.json()["id"]
        if i % 2 == 0:
            client.patch(
                f"/api/v1/tickets/{t_id}/assign",
                json={"assignee_id": agent_user.id},
                headers=agent_auth_headers,
            )

    queries_1 = []
    def record_query_1(conn, cursor, statement, parameters, context, executemany):
        # Ignore transaction savepoint/rollback queries
        stmt = statement.strip().upper()
        if stmt.startswith("SELECT"):
            queries_1.append(statement)

    # Query with page_size=1
    event.listen(test_engine, "before_cursor_execute", record_query_1)
    try:
        res1 = client.get("/api/v1/tickets?page_size=1", headers=agent_auth_headers)
        assert res1.status_code == 200
        assert len(res1.json()["items"]) == 1
    finally:
        event.remove(test_engine, "before_cursor_execute", record_query_1)

    queries_5 = []
    def record_query_5(conn, cursor, statement, parameters, context, executemany):
        stmt = statement.strip().upper()
        if stmt.startswith("SELECT"):
            queries_5.append(statement)

    # Query with page_size=5
    event.listen(test_engine, "before_cursor_execute", record_query_5)
    try:
        res5 = client.get("/api/v1/tickets?page_size=5", headers=agent_auth_headers)
        assert res5.status_code == 200
        assert len(res5.json()["items"]) == 5
    finally:
        event.remove(test_engine, "before_cursor_execute", record_query_5)

    # In both cases, exactly the same number of SELECT statements must be executed (1 count + 1 joined fetch = 2)
    assert len(queries_1) == len(queries_5), (
        f"N+1 detected! page_size=1 executed {len(queries_1)} SELECTs, "
        f"page_size=5 executed {len(queries_5)} SELECTs."
    )
