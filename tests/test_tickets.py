import time
from fastapi.testclient import TestClient

from app.models.user import User


def test_create_ticket(client: TestClient, requester_user: User, requester_auth_headers: dict[str, str]):
    """Test creating a ticket sets requester_id from logged-in user and status to 'open'."""
    payload = {
        "title": "VPN connection failing",
        "description": "Cannot connect to corporate VPN since morning.",
        "priority": "high",
    }
    response = client.post("/api/v1/tickets", json=payload, headers=requester_auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "VPN connection failing"
    assert data["description"] == "Cannot connect to corporate VPN since morning."
    assert data["priority"] == "high"
    assert data["status"] == "open"
    assert data["requester_id"] == requester_user.id
    assert data["assignee_id"] is None
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_requester_cannot_see_another_requesters_ticket(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    second_requester_auth_headers: dict[str, str],
):
    """Test that a requester receives 404 (not 403) when requesting another user's ticket."""
    create_res = client.post(
        "/api/v1/tickets",
        json={"title": "Private ticket", "description": "Details here"},
        headers=requester_auth_headers,
    )
    assert create_res.status_code == 201
    ticket_id = create_res.json()["id"]

    # Second requester attempts to view ticket
    view_res = client.get(f"/api/v1/tickets/{ticket_id}", headers=second_requester_auth_headers)
    assert view_res.status_code == 404
    data = view_res.json()
    assert "error" in data
    assert data["error"]["message"] == "Ticket not found"


def test_requester_list_only_sees_own_tickets(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    second_requester_auth_headers: dict[str, str],
):
    """Test that GET /tickets returns only tickets belonging to the requesting user."""
    client.post(
        "/api/v1/tickets",
        json={"title": "User 1 Ticket", "description": "Desc 1"},
        headers=requester_auth_headers,
    )
    client.post(
        "/api/v1/tickets",
        json={"title": "User 2 Ticket", "description": "Desc 2"},
        headers=second_requester_auth_headers,
    )

    res1 = client.get("/api/v1/tickets", headers=requester_auth_headers)
    assert res1.status_code == 200
    data1 = res1.json()
    assert "items" in data1
    assert data1["total"] >= 1
    titles1 = [t["title"] for t in data1["items"]]
    assert "User 1 Ticket" in titles1
    assert "User 2 Ticket" not in titles1

    res2 = client.get("/api/v1/tickets", headers=second_requester_auth_headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert "items" in data2
    assert data2["total"] >= 1
    titles2 = [t["title"] for t in data2["items"]]
    assert "User 2 Ticket" in titles2
    assert "User 1 Ticket" not in titles2


def test_agent_and_admin_see_all_tickets(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    second_requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
    admin_auth_headers: dict[str, str],
):
    """Test that agents and admins see all tickets from all users."""
    client.post(
        "/api/v1/tickets",
        json={"title": "Ticket Alpha", "description": "Desc A"},
        headers=requester_auth_headers,
    )
    client.post(
        "/api/v1/tickets",
        json={"title": "Ticket Beta", "description": "Desc B"},
        headers=second_requester_auth_headers,
    )

    agent_res = client.get("/api/v1/tickets", headers=agent_auth_headers)
    assert agent_res.status_code == 200
    agent_data = agent_res.json()
    assert "items" in agent_data
    agent_titles = [t["title"] for t in agent_data["items"]]
    assert "Ticket Alpha" in agent_titles
    assert "Ticket Beta" in agent_titles

    admin_res = client.get("/api/v1/tickets", headers=admin_auth_headers)
    assert admin_res.status_code == 200
    admin_data = admin_res.json()
    assert "items" in admin_data
    admin_titles = [t["title"] for t in admin_data["items"]]
    assert "Ticket Alpha" in admin_titles
    assert "Ticket Beta" in admin_titles


def test_status_workflow_allowed_moves(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
):
    """Test all valid status moves: open -> in_progress -> resolved -> in_progress (reopen) -> resolved -> closed."""
    res = client.post(
        "/api/v1/tickets",
        json={"title": "Workflow ticket", "description": "Status path test"},
        headers=requester_auth_headers,
    )
    ticket_id = res.json()["id"]

    # 1. open -> in_progress
    move1 = client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "in_progress"},
    )
    assert move1.status_code == 200
    assert move1.json()["status"] == "in_progress"

    # 2. in_progress -> resolved
    move2 = client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "resolved"},
    )
    assert move2.status_code == 200
    assert move2.json()["status"] == "resolved"

    # 3. resolved -> in_progress (reopen)
    move3 = client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "in_progress"},
    )
    assert move3.status_code == 200
    assert move3.json()["status"] == "in_progress"

    # 4. in_progress -> resolved
    move4 = client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "resolved"},
    )
    assert move4.status_code == 200
    assert move4.json()["status"] == "resolved"

    # 5. resolved -> closed
    move5 = client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "closed"},
    )
    assert move5.status_code == 200
    assert move5.json()["status"] == "closed"


def test_status_workflow_invalid_moves_return_409(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
):
    """Test that invalid status transitions return 409 Conflict with formatted error."""
    # Test 1: open -> resolved (invalid)
    t1 = client.post(
        "/api/v1/tickets",
        json={"title": "Invalid 1", "description": "Desc"},
        headers=requester_auth_headers,
    ).json()["id"]
    res1 = client.patch(
        f"/api/v1/tickets/{t1}/status",
        headers=agent_auth_headers,
        json={"status": "resolved"},
    )
    assert res1.status_code == 409
    assert "Cannot transition ticket status" in res1.json()["error"]["message"]

    # Test 2: open -> closed (invalid)
    res2 = client.patch(
        f"/api/v1/tickets/{t1}/status",
        headers=agent_auth_headers,
        json={"status": "closed"},
    )
    assert res2.status_code == 409
    assert "Cannot transition ticket status" in res2.json()["error"]["message"]

    # Move t1 to in_progress
    client.patch(
        f"/api/v1/tickets/{t1}/status",
        headers=agent_auth_headers,
        json={"status": "in_progress"},
    )

    # Test 3: in_progress -> closed (invalid, must be resolved first)
    res3 = client.patch(
        f"/api/v1/tickets/{t1}/status",
        headers=agent_auth_headers,
        json={"status": "closed"},
    )
    assert res3.status_code == 409
    assert "Cannot transition ticket status" in res3.json()["error"]["message"]

    # Resolve and close t1
    client.patch(f"/api/v1/tickets/{t1}/status", headers=agent_auth_headers, json={"status": "resolved"})
    client.patch(f"/api/v1/tickets/{t1}/status", headers=agent_auth_headers, json={"status": "closed"})

    # Test 4: closed -> in_progress (invalid, closed is terminal)
    res4 = client.patch(
        f"/api/v1/tickets/{t1}/status",
        headers=agent_auth_headers,
        json={"status": "in_progress"},
    )
    assert res4.status_code == 409
    assert "Cannot transition ticket status" in res4.json()["error"]["message"]


def test_requester_cannot_change_status(
    client: TestClient,
    requester_auth_headers: dict[str, str],
):
    """Test that a requester receives 403 when trying to change ticket status."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "My ticket", "description": "Desc"},
        headers=requester_auth_headers,
    ).json()["id"]

    response = client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=requester_auth_headers,
        json={"status": "in_progress"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["message"] == "Only agents and admins can update ticket status"


def test_assign_ticket_success_moves_open_to_in_progress(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
    agent_user: User,
):
    """Test assigning an open ticket to an active agent moves status to in_progress."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "Unassigned ticket", "description": "Needs agent"},
        headers=requester_auth_headers,
    ).json()["id"]

    response = client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        headers=agent_auth_headers,
        json={"assignee_id": agent_user.id},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["assignee_id"] == agent_user.id
    assert data["status"] == "in_progress"


def test_assign_ticket_non_agent_returns_422(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    second_requester_user: User,
    agent_auth_headers: dict[str, str],
):
    """Test assigning a ticket to a non-agent user returns 422."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "Ticket", "description": "Desc"},
        headers=requester_auth_headers,
    ).json()["id"]

    response = client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        headers=agent_auth_headers,
        json={"assignee_id": second_requester_user.id},
    )
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Assignee must be an active agent"


def test_assign_ticket_missing_user_returns_404(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
):
    """Test assigning a ticket to a non-existent user ID returns 404."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "Ticket", "description": "Desc"},
        headers=requester_auth_headers,
    ).json()["id"]

    response = client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        headers=agent_auth_headers,
        json={"assignee_id": 999999},
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Assignee user not found"


def test_requester_cannot_assign_ticket(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    agent_user: User,
):
    """Test that a requester receives 403 when trying to assign a ticket."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "Ticket", "description": "Desc"},
        headers=requester_auth_headers,
    ).json()["id"]

    response = client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        headers=requester_auth_headers,
        json={"assignee_id": agent_user.id},
    )
    assert response.status_code == 403
    assert response.json()["error"]["message"] == "Only agents and admins can assign tickets"


def test_edit_ticket_rules(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
    admin_auth_headers: dict[str, str],
):
    """Test editing ticket title/description/priority: allowed for owner while open, or admin."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "Initial Title", "description": "Initial Desc", "priority": "low"},
        headers=requester_auth_headers,
    ).json()["id"]

    # 1. Owner edits while open -> 200
    res1 = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=requester_auth_headers,
        json={"title": "Updated Title", "priority": "high"},
    )
    assert res1.status_code == 200
    assert res1.json()["title"] == "Updated Title"
    assert res1.json()["priority"] == "high"

    # Move ticket to in_progress
    client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "in_progress"},
    )

    # 2. Owner edits while in_progress -> 403 Forbidden
    res2 = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=requester_auth_headers,
        json={"title": "Should Fail"},
    )
    assert res2.status_code == 403
    assert res2.json()["error"]["message"] == "Requesters can only edit tickets while they are open"

    # 3. Admin edits while in_progress -> 200 OK
    res3 = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=admin_auth_headers,
        json={"title": "Admin Override Title"},
    )
    assert res3.status_code == 200
    assert res3.json()["title"] == "Admin Override Title"


def test_updated_at_changes_after_update(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    admin_auth_headers: dict[str, str],
):
    """Test that updated_at timestamp changes after a ticket is modified."""
    ticket = client.post(
        "/api/v1/tickets",
        json={"title": "Timestamp Test", "description": "Checking updated_at"},
        headers=requester_auth_headers,
    ).json()

    initial_updated_at = ticket["updated_at"]
    time.sleep(0.01)  # small pause to guarantee different timestamp

    update_res = client.patch(
        f"/api/v1/tickets/{ticket['id']}",
        headers=admin_auth_headers,
        json={"description": "Updated content"},
    )
    assert update_res.status_code == 200
    new_updated_at = update_res.json()["updated_at"]
    assert new_updated_at > initial_updated_at


def test_assign_closed_ticket_returns_409(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
    agent_user: User,
):
    """Test assigning a closed ticket returns 409 Conflict."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "To be closed", "description": "Desc"},
        headers=requester_auth_headers,
    ).json()["id"]

    # Transition to closed: open -> in_progress -> resolved -> closed
    client.patch(f"/api/v1/tickets/{ticket_id}/status", headers=agent_auth_headers, json={"status": "in_progress"})
    client.patch(f"/api/v1/tickets/{ticket_id}/status", headers=agent_auth_headers, json={"status": "resolved"})
    client.patch(f"/api/v1/tickets/{ticket_id}/status", headers=agent_auth_headers, json={"status": "closed"})

    # Attempt to assign the closed ticket
    response = client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        headers=agent_auth_headers,
        json={"assignee_id": agent_user.id},
    )
    assert response.status_code == 409
    data = response.json()
    assert "error" in data
    assert data["error"]["message"] == "Cannot assign a closed ticket"


def test_ticket_category_default_and_validation(
    client: TestClient,
    requester_auth_headers: dict[str, str],
):
    """Test category default is 'other', custom category works, and invalid category returns 422."""
    # 1. Default category
    res1 = client.post(
        "/api/v1/tickets",
        json={"title": "Default Category Ticket", "description": "Desc"},
        headers=requester_auth_headers,
    )
    assert res1.status_code == 201
    assert res1.json()["category"] == "other"

    # 2. Explicit valid category
    res2 = client.post(
        "/api/v1/tickets",
        json={"title": "Network Ticket", "description": "Desc", "category": "network"},
        headers=requester_auth_headers,
    )
    assert res2.status_code == 201
    assert res2.json()["category"] == "network"

    # 3. Invalid category -> 422
    res3 = client.post(
        "/api/v1/tickets",
        json={"title": "Invalid Category Ticket", "description": "Desc", "category": "invalid_cat"},
        headers=requester_auth_headers,
    )
    assert res3.status_code == 422
    assert "error" in res3.json()


def test_ticket_category_filter(
    client: TestClient,
    requester_auth_headers: dict[str, str],
):
    """Test filtering tickets by category, and invalid category filter returning 422."""
    client.post(
        "/api/v1/tickets",
        json={"title": "Filter HW", "description": "Desc", "category": "hardware"},
        headers=requester_auth_headers,
    )
    client.post(
        "/api/v1/tickets",
        json={"title": "Filter SW", "description": "Desc", "category": "software"},
        headers=requester_auth_headers,
    )

    # Valid category filter
    res_hw = client.get("/api/v1/tickets?category=hardware", headers=requester_auth_headers)
    assert res_hw.status_code == 200
    hw_items = res_hw.json()["items"]
    assert all(item["category"] == "hardware" for item in hw_items)
    assert any(item["title"] == "Filter HW" for item in hw_items)
    assert not any(item["title"] == "Filter SW" for item in hw_items)

    # Invalid category filter -> 422
    res_invalid = client.get("/api/v1/tickets?category=nonexistent", headers=requester_auth_headers)
    assert res_invalid.status_code == 422
    assert "error" in res_invalid.json()


def test_ticket_category_update_permissions(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    second_requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
    admin_auth_headers: dict[str, str],
):
    """
    Test category update permissions:
    - Ticket owner can update category while open.
    - Ticket owner cannot update category while in_progress (403).
    - Agents can update category anytime (while open or in_progress).
    - Agents cannot update title/description/priority (403).
    - Admins can update category anytime.
    - Other requesters cannot edit ticket.
    """
    # Create ticket as requester
    create_res = client.post(
        "/api/v1/tickets",
        json={"title": "Permissions Test", "description": "Desc", "category": "other"},
        headers=requester_auth_headers,
    )
    ticket_id = create_res.json()["id"]

    # 1. Owner updates category while open -> 200
    res1 = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"category": "software"},
        headers=requester_auth_headers,
    )
    assert res1.status_code == 200
    assert res1.json()["category"] == "software"

    # Transition to in_progress via agent
    client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"status": "in_progress"},
        headers=agent_auth_headers,
    )

    # 2. Owner updates category while in_progress -> 403
    res2 = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"category": "hardware"},
        headers=requester_auth_headers,
    )
    assert res2.status_code == 403
    assert res2.json()["error"]["message"] == "Requesters can only edit tickets while they are open"

    # 3. Agent updates category while in_progress -> 200
    res3 = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"category": "hardware"},
        headers=agent_auth_headers,
    )
    assert res3.status_code == 200
    assert res3.json()["category"] == "hardware"

    # 4. Agent tries to update title -> 403
    res4 = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"title": "Agent Hacked Title"},
        headers=agent_auth_headers,
    )
    assert res4.status_code == 403
    assert res4.json()["error"]["message"] == "Agents can only update ticket category"

    # 5. Admin updates category -> 200
    res5 = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"category": "access"},
        headers=admin_auth_headers,
    )
    assert res5.status_code == 200
    assert res5.json()["category"] == "access"

    # 6. Another requester tries to update ticket -> 404 (not visible to them)
    res6 = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"category": "email"},
        headers=second_requester_auth_headers,
    )
    assert res6.status_code == 404


