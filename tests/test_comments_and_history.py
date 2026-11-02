from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.comment import TicketComment
from app.models.enums import TicketStatus
from app.models.history import TicketStatusHistory
from app.models.user import User


def test_add_comment(
    client: TestClient,
    requester_user: User,
    requester_auth_headers: dict[str, str],
):
    """Test adding a normal comment to a ticket by the ticket owner."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "Comment Test Ticket", "description": "Needs assistance"},
        headers=requester_auth_headers,
    ).json()["id"]

    response = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=requester_auth_headers,
        json={"body": "Any update on this issue?"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["ticket_id"] == ticket_id
    assert data["author_id"] == requester_user.id
    assert data["body"] == "Any update on this issue?"
    assert data["is_internal"] is False
    assert "id" in data
    assert "created_at" in data


def test_internal_comment_visibility(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
):
    """Test internal comment is hidden from requester but visible to staff."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "Internal Note Test", "description": "Hardware failure"},
        headers=requester_auth_headers,
    ).json()["id"]

    # Public comment by requester
    client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=requester_auth_headers,
        json={"body": "Public message from requester", "is_internal": False},
    )

    # Internal note by agent
    agent_comment_res = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=agent_auth_headers,
        json={"body": "Internal agent note: escalating to vendor.", "is_internal": True},
    )
    assert agent_comment_res.status_code == 201
    assert agent_comment_res.json()["is_internal"] is True

    # Requester reads comments -> only sees public comment
    req_view = client.get(f"/api/v1/tickets/{ticket_id}/comments", headers=requester_auth_headers)
    assert req_view.status_code == 200
    req_bodies = [c["body"] for c in req_view.json()]
    assert "Public message from requester" in req_bodies
    assert "Internal agent note: escalating to vendor." not in req_bodies

    # Agent reads comments -> sees both comments
    agent_view = client.get(f"/api/v1/tickets/{ticket_id}/comments", headers=agent_auth_headers)
    assert agent_view.status_code == 200
    agent_bodies = [c["body"] for c in agent_view.json()]
    assert "Public message from requester" in agent_bodies
    assert "Internal agent note: escalating to vendor." in agent_bodies


def test_requester_cannot_post_internal_comment(
    client: TestClient,
    requester_auth_headers: dict[str, str],
):
    """Test that a requester receives 403 when trying to set is_internal=true."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "Ticket", "description": "Desc"},
        headers=requester_auth_headers,
    ).json()["id"]

    response = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=requester_auth_headers,
        json={"body": "Attempted secret note", "is_internal": True},
    )
    assert response.status_code == 403
    assert response.json()["error"]["message"] == "Requesters cannot create internal comments"


def test_comment_on_closed_ticket_returns_409(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
):
    """Test that attempting to comment on a closed ticket returns 409 Conflict."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "Ticket to close", "description": "Desc"},
        headers=requester_auth_headers,
    ).json()["id"]

    # Transition to closed: open -> in_progress -> resolved -> closed
    client.patch(f"/api/v1/tickets/{ticket_id}/status", headers=agent_auth_headers, json={"status": "in_progress"})
    client.patch(f"/api/v1/tickets/{ticket_id}/status", headers=agent_auth_headers, json={"status": "resolved"})
    client.patch(f"/api/v1/tickets/{ticket_id}/status", headers=agent_auth_headers, json={"status": "closed"})

    # Try commenting on closed ticket as requester
    req_res = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=requester_auth_headers,
        json={"body": "Can I still comment?"},
    )
    assert req_res.status_code == 409
    assert req_res.json()["error"]["message"] == "Cannot add comments to a closed ticket"

    # Try commenting on closed ticket as agent
    agent_res = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=agent_auth_headers,
        json={"body": "Agent comment on closed"},
    )
    assert agent_res.status_code == 409
    assert agent_res.json()["error"]["message"] == "Cannot add comments to a closed ticket"


def test_comment_body_length_validation(
    client: TestClient,
    requester_auth_headers: dict[str, str],
):
    """Test that empty comment body and body > 2000 chars return 422."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "Ticket", "description": "Desc"},
        headers=requester_auth_headers,
    ).json()["id"]

    # Empty body
    res_empty = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=requester_auth_headers,
        json={"body": ""},
    )
    assert res_empty.status_code == 422
    assert "error" in res_empty.json()
    assert "body" in res_empty.json()["error"]["message"].lower()

    # Body > 2000 characters
    res_toolong = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=requester_auth_headers,
        json={"body": "x" * 2001},
    )
    assert res_toolong.status_code == 422
    assert "error" in res_toolong.json()
    assert "body" in res_toolong.json()["error"]["message"].lower()


def test_history_entries_in_order(
    client: TestClient,
    requester_user: User,
    agent_user: User,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
):
    """Test that status history records correct entries after create, assign, and each status change."""
    # 1. Create ticket (open)
    create_res = client.post(
        "/api/v1/tickets",
        json={"title": "History Trail Ticket", "description": "Lifecycle test"},
        headers=requester_auth_headers,
    )
    ticket_id = create_res.json()["id"]

    # 2. Assign ticket (moves open -> in_progress)
    client.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        headers=agent_auth_headers,
        json={"assignee_id": agent_user.id},
    )

    # 3. Status in_progress -> resolved
    client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "resolved"},
    )

    # 4. Status resolved -> in_progress (reopen)
    client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "in_progress"},
    )

    # 5. Status in_progress -> resolved
    client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "resolved"},
    )

    # 6. Status resolved -> closed
    client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "closed"},
    )

    # Fetch status history
    hist_res = client.get(f"/api/v1/tickets/{ticket_id}/history", headers=requester_auth_headers)
    assert hist_res.status_code == 200
    history = hist_res.json()

    assert len(history) == 6

    # Verify each step in sequence
    assert history[0]["from_status"] is None
    assert history[0]["to_status"] == "open"
    assert history[0]["changed_by_id"] == requester_user.id

    assert history[1]["from_status"] == "open"
    assert history[1]["to_status"] == "in_progress"
    assert history[1]["changed_by_id"] == agent_user.id

    assert history[2]["from_status"] == "in_progress"
    assert history[2]["to_status"] == "resolved"
    assert history[2]["changed_by_id"] == agent_user.id

    assert history[3]["from_status"] == "resolved"
    assert history[3]["to_status"] == "in_progress"
    assert history[3]["changed_by_id"] == agent_user.id

    assert history[4]["from_status"] == "in_progress"
    assert history[4]["to_status"] == "resolved"
    assert history[4]["changed_by_id"] == agent_user.id

    assert history[5]["from_status"] == "resolved"
    assert history[5]["to_status"] == "closed"
    assert history[5]["changed_by_id"] == agent_user.id


def test_comments_and_history_ordering_with_identical_timestamps(
    client: TestClient,
    db_session: Session,
    requester_user: User,
    agent_user: User,
    requester_auth_headers: dict[str, str],
):
    """
    Test that when multiple comments or status history rows have the exact same created_at timestamp,
    they are deterministically ordered by id ascending.
    """
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "Timestamp Tie Ticket", "description": "Desc"},
        headers=requester_auth_headers,
    ).json()["id"]

    # Use a future timestamp so all 3 entries share the exact same timestamp after initial creation
    same_timestamp = datetime.now(timezone.utc) + timedelta(minutes=5)

    # 1. Insert multiple comments with identical timestamp directly into db
    c1 = TicketComment(ticket_id=ticket_id, author_id=requester_user.id, body="Comment A", created_at=same_timestamp)
    c2 = TicketComment(ticket_id=ticket_id, author_id=requester_user.id, body="Comment B", created_at=same_timestamp)
    c3 = TicketComment(ticket_id=ticket_id, author_id=requester_user.id, body="Comment C", created_at=same_timestamp)
    db_session.add_all([c1, c2, c3])

    # 2. Insert multiple history rows with identical timestamp
    h1 = TicketStatusHistory(ticket_id=ticket_id, changed_by_id=agent_user.id, from_status=TicketStatus.OPEN, to_status=TicketStatus.IN_PROGRESS, created_at=same_timestamp)
    h2 = TicketStatusHistory(ticket_id=ticket_id, changed_by_id=agent_user.id, from_status=TicketStatus.IN_PROGRESS, to_status=TicketStatus.RESOLVED, created_at=same_timestamp)
    h3 = TicketStatusHistory(ticket_id=ticket_id, changed_by_id=agent_user.id, from_status=TicketStatus.RESOLVED, to_status=TicketStatus.CLOSED, created_at=same_timestamp)
    db_session.add_all([h1, h2, h3])
    db_session.commit()

    # Verify comments ordering by id ascending
    comment_res = client.get(f"/api/v1/tickets/{ticket_id}/comments", headers=requester_auth_headers)
    assert comment_res.status_code == 200
    comment_ids = [c["id"] for c in comment_res.json()]
    assert comment_ids == sorted(comment_ids)
    assert [c["body"] for c in comment_res.json()] == ["Comment A", "Comment B", "Comment C"]

    # Verify history ordering by id ascending
    history_res = client.get(f"/api/v1/tickets/{ticket_id}/history", headers=requester_auth_headers)
    assert history_res.status_code == 200
    history_ids = [h["id"] for h in history_res.json()]
    assert history_ids == sorted(history_ids)


def test_other_requester_gets_404_on_comments_and_history(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    second_requester_auth_headers: dict[str, str],
):
    """Test that a requester asking for another person's ticket gets 404 on comments and history."""
    ticket_id = client.post(
        "/api/v1/tickets",
        json={"title": "Private User Ticket", "description": "Sensitive details"},
        headers=requester_auth_headers,
    ).json()["id"]

    # Second requester attempts to post comment
    post_comment_res = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=second_requester_auth_headers,
        json={"body": "Intruder comment"},
    )
    assert post_comment_res.status_code == 404
    assert post_comment_res.json()["error"]["message"] == "Ticket not found"

    # Second requester attempts to read comments
    get_comments_res = client.get(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=second_requester_auth_headers,
    )
    assert get_comments_res.status_code == 404
    assert get_comments_res.json()["error"]["message"] == "Ticket not found"

    # Second requester attempts to read history
    get_history_res = client.get(
        f"/api/v1/tickets/{ticket_id}/history",
        headers=second_requester_auth_headers,
    )
    assert get_history_res.status_code == 404
    assert get_history_res.json()["error"]["message"] == "Ticket not found"
