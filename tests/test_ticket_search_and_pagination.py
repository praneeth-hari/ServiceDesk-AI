from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import TicketPriority, TicketStatus
from app.models.ticket import Ticket
from app.models.user import User


def test_pagination_pages_and_total(
    client: TestClient,
    requester_auth_headers: dict[str, str],
):
    """Test pagination: page 1 and page 2 return different items and total is correct."""
    # Create 5 tickets
    for i in range(1, 6):
        client.post(
            "/api/v1/tickets",
            json={"title": f"Pagination Ticket {i}", "description": f"Desc {i}"},
            headers=requester_auth_headers,
        )

    # Page 1 with page_size=2
    res_p1 = client.get("/api/v1/tickets?page=1&page_size=2", headers=requester_auth_headers)
    assert res_p1.status_code == 200
    data_p1 = res_p1.json()
    assert data_p1["page"] == 1
    assert data_p1["page_size"] == 2
    assert data_p1["total"] == 5
    assert len(data_p1["items"]) == 2
    p1_ids = [item["id"] for item in data_p1["items"]]

    # Page 2 with page_size=2
    res_p2 = client.get("/api/v1/tickets?page=2&page_size=2", headers=requester_auth_headers)
    assert res_p2.status_code == 200
    data_p2 = res_p2.json()
    assert data_p2["page"] == 2
    assert data_p2["page_size"] == 2
    assert data_p2["total"] == 5
    assert len(data_p2["items"]) == 2
    p2_ids = [item["id"] for item in data_p2["items"]]

    # Verify page 1 and page 2 returned different items
    assert set(p1_ids).isdisjoint(set(p2_ids))

    # Page 3 with page_size=2
    res_p3 = client.get("/api/v1/tickets?page=3&page_size=2", headers=requester_auth_headers)
    assert res_p3.status_code == 200
    data_p3 = res_p3.json()
    assert len(data_p3["items"]) == 1

    # Page 4 with page_size=2 -> empty items
    res_p4 = client.get("/api/v1/tickets?page=4&page_size=2", headers=requester_auth_headers)
    assert res_p4.status_code == 200
    data_p4 = res_p4.json()
    assert len(data_p4["items"]) == 0
    assert data_p4["total"] == 5


def test_page_size_validation_and_errors(
    client: TestClient,
    requester_auth_headers: dict[str, str],
):
    """Test validation errors: page_size > 100, page < 1, and invalid query values give 422 in error format."""
    # page_size > 100
    res1 = client.get("/api/v1/tickets?page_size=101", headers=requester_auth_headers)
    assert res1.status_code == 422
    assert "error" in res1.json()
    assert "page_size" in res1.json()["error"]["message"]

    # page < 1
    res2 = client.get("/api/v1/tickets?page=0", headers=requester_auth_headers)
    assert res2.status_code == 422
    assert "error" in res2.json()
    assert "page" in res2.json()["error"]["message"]

    # invalid sort_by
    res3 = client.get("/api/v1/tickets?sort_by=invalid_col", headers=requester_auth_headers)
    assert res3.status_code == 422
    assert "error" in res3.json()

    # invalid order
    res4 = client.get("/api/v1/tickets?order=sideways", headers=requester_auth_headers)
    assert res4.status_code == 422
    assert "error" in res4.json()

    # invalid status
    res5 = client.get("/api/v1/tickets?status=unknown", headers=requester_auth_headers)
    assert res5.status_code == 422
    assert "error" in res5.json()

    # invalid priority
    res6 = client.get("/api/v1/tickets?priority=extreme", headers=requester_auth_headers)
    assert res6.status_code == 422
    assert "error" in res6.json()


def test_filters_individual_and_combined(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
):
    """Test filtering by status, priority, assignee_id, overdue, and combined filters."""
    now = datetime.now(timezone.utc)

    # Ticket 1: open, urgent, assigned to agent_user, due in the future
    t1 = Ticket(
        title="Ticket 1 urgent",
        description="High urgency issue",
        status=TicketStatus.OPEN,
        priority=TicketPriority.URGENT,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=now + timedelta(days=2),
        created_at=now,
        updated_at=now,
    )
    # Ticket 2: in_progress, low, assigned to agent_user, overdue (due in past)
    t2 = Ticket(
        title="Ticket 2 low overdue",
        description="Routine task overdue",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=now - timedelta(days=1),
        created_at=now - timedelta(days=5),
        updated_at=now,
    )
    # Ticket 3: resolved, high, unassigned, due in past (but not overdue because resolved)
    t3 = Ticket(
        title="Ticket 3 resolved",
        description="Fix complete",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.HIGH,
        requester_id=requester_user.id,
        assignee_id=None,
        due_at=now - timedelta(days=2),
        created_at=now - timedelta(days=4),
        updated_at=now,
    )
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    # 1. Filter by status=open
    res_status = client.get("/api/v1/tickets?status=open", headers=agent_auth_headers)
    assert res_status.status_code == 200
    assert [t["id"] for t in res_status.json()["items"]] == [t1.id]

    # 2. Filter by priority=low
    res_prio = client.get("/api/v1/tickets?priority=low", headers=agent_auth_headers)
    assert res_prio.status_code == 200
    assert [t["id"] for t in res_prio.json()["items"]] == [t2.id]

    # 3. Filter by assignee_id
    res_assign = client.get(f"/api/v1/tickets?assignee_id={agent_user.id}", headers=agent_auth_headers)
    assert res_assign.status_code == 200
    assignee_ids = {t["id"] for t in res_assign.json()["items"]}
    assert assignee_ids == {t1.id, t2.id}

    # 4. Filter by overdue=true
    res_overdue = client.get("/api/v1/tickets?overdue=true", headers=agent_auth_headers)
    assert res_overdue.status_code == 200
    assert [t["id"] for t in res_overdue.json()["items"]] == [t2.id]

    # 5. Filter by overdue=false
    res_not_overdue = client.get("/api/v1/tickets?overdue=false", headers=agent_auth_headers)
    assert res_not_overdue.status_code == 200
    not_overdue_ids = {t["id"] for t in res_not_overdue.json()["items"]}
    assert t1.id in not_overdue_ids
    assert t3.id in not_overdue_ids
    assert t2.id not in not_overdue_ids

    # 6. Combined filters: status=in_progress & priority=low & overdue=true
    res_comb = client.get(
        f"/api/v1/tickets?status=in_progress&priority=low&assignee_id={agent_user.id}&overdue=true",
        headers=agent_auth_headers,
    )
    assert res_comb.status_code == 200
    assert [t["id"] for t in res_comb.json()["items"]] == [t2.id]

    # 7. Combined filter that matches nothing: status=open & priority=low
    res_none = client.get("/api/v1/tickets?status=open&priority=low", headers=agent_auth_headers)
    assert res_none.status_code == 200
    assert len(res_none.json()["items"]) == 0
    assert res_none.json()["total"] == 0


def test_sorting_asc_and_desc(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    db_session: Session,
    requester_user: User,
):
    """Test sorting by created_at, updated_at, and due_at ascending and descending."""
    now = datetime.now(timezone.utc)

    t1 = Ticket(
        title="Sort 1",
        description="Desc",
        status=TicketStatus.OPEN,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        created_at=now - timedelta(hours=3),
        updated_at=now - timedelta(hours=1),
        due_at=now + timedelta(hours=10),
    )
    t2 = Ticket(
        title="Sort 2",
        description="Desc",
        status=TicketStatus.OPEN,
        priority=TicketPriority.HIGH,
        requester_id=requester_user.id,
        created_at=now - timedelta(hours=2),
        updated_at=now - timedelta(hours=2),
        due_at=now + timedelta(hours=5),
    )
    t3 = Ticket(
        title="Sort 3",
        description="Desc",
        status=TicketStatus.OPEN,
        priority=TicketPriority.URGENT,
        requester_id=requester_user.id,
        created_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=3),
        due_at=now + timedelta(hours=20),
    )
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    # Sort by created_at desc (default)
    res_desc = client.get("/api/v1/tickets?sort_by=created_at&order=desc", headers=requester_auth_headers)
    assert res_desc.status_code == 200
    ids_desc = [t["id"] for t in res_desc.json()["items"]]
    assert ids_desc == [t3.id, t2.id, t1.id]

    # Sort by created_at asc
    res_asc = client.get("/api/v1/tickets?sort_by=created_at&order=asc", headers=requester_auth_headers)
    assert res_asc.status_code == 200
    ids_asc = [t["id"] for t in res_asc.json()["items"]]
    assert ids_asc == [t1.id, t2.id, t3.id]

    # Sort by updated_at asc
    res_upd_asc = client.get("/api/v1/tickets?sort_by=updated_at&order=asc", headers=requester_auth_headers)
    assert res_upd_asc.status_code == 200
    ids_upd_asc = [t["id"] for t in res_upd_asc.json()["items"]]
    assert ids_upd_asc == [t3.id, t2.id, t1.id]

    # Sort by due_at asc
    res_due_asc = client.get("/api/v1/tickets?sort_by=due_at&order=asc", headers=requester_auth_headers)
    assert res_due_asc.status_code == 200
    ids_due_asc = [t["id"] for t in res_due_asc.json()["items"]]
    assert ids_due_asc == [t2.id, t1.id, t3.id]


def test_keyword_search_escaping_wildcards(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    db_session: Session,
    requester_user: User,
):
    """
    Test keyword search 'q':
    - Searches title and description case-insensitively.
    - Properly escapes '%' and '_' so they are treated as literal characters, not SQL wildcards.
    """
    now = datetime.now(timezone.utc)

    # Tickets with '%'
    t_percent = Ticket(
        title="Discount 100% Guaranteed",
        description="Normal promotion details",
        status=TicketStatus.OPEN,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        created_at=now,
        updated_at=now,
    )
    t_no_percent = Ticket(
        title="Discount 100 dollars",
        description="Normal cash discount",
        status=TicketStatus.OPEN,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        created_at=now,
        updated_at=now,
    )

    # Tickets with '_'
    t_underscore = Ticket(
        title="Database migration",
        description="File is named db_backup.sql",
        status=TicketStatus.OPEN,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        created_at=now,
        updated_at=now,
    )
    t_no_underscore = Ticket(
        title="Database migration test",
        description="File is named dbXbackup.sql",
        status=TicketStatus.OPEN,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        created_at=now,
        updated_at=now,
    )

    db_session.add_all([t_percent, t_no_percent, t_underscore, t_no_underscore])
    db_session.commit()

    # 1. Search for literal '%': "100%" should match ONLY t_percent
    res_percent = client.get("/api/v1/tickets?q=100%", headers=requester_auth_headers)
    assert res_percent.status_code == 200
    percent_items = res_percent.json()["items"]
    assert len(percent_items) == 1
    assert percent_items[0]["id"] == t_percent.id

    # 2. Search for literal '_': "db_backup" should match ONLY t_underscore, not t_no_underscore
    res_under = client.get("/api/v1/tickets?q=db_backup", headers=requester_auth_headers)
    assert res_under.status_code == 200
    under_items = res_under.json()["items"]
    assert len(under_items) == 1
    assert under_items[0]["id"] == t_underscore.id

    # 3. Case-insensitive search: "guaranteed" matches "Guaranteed"
    res_case = client.get("/api/v1/tickets?q=guaranteed", headers=requester_auth_headers)
    assert res_case.status_code == 200
    assert len(res_case.json()["items"]) == 1
    assert res_case.json()["items"][0]["id"] == t_percent.id

    # 4. Search matches description: "promotion details" matches t_percent
    res_desc = client.get("/api/v1/tickets?q=promotion", headers=requester_auth_headers)
    assert res_desc.status_code == 200
    assert len(res_desc.json()["items"]) == 1
    assert res_desc.json()["items"][0]["id"] == t_percent.id


def test_requester_visibility_cannot_be_bypassed_with_filters_or_q(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    second_requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
    second_requester_user: User,
):
    """
    Test that a requester only ever sees their own tickets:
    Even when passing filters (e.g. assignee_id) or search query ('q') targeting another user's ticket,
    the other user's tickets are NEVER returned to the requester.
    Agents, on the other hand, can see all tickets matching the filters.
    """
    now = datetime.now(timezone.utc)

    # Requester 1 creates a ticket with confidential query keyword and assigned to agent
    t_secret = Ticket(
        title="Confidential Internal Audit",
        description="Sensitive system security evaluation",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.URGENT,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        created_at=now,
        updated_at=now,
    )
    # Requester 2 creates a public ticket
    t_public = Ticket(
        title="Public Keyboard Replacement",
        description="Keys are sticking",
        status=TicketStatus.OPEN,
        priority=TicketPriority.LOW,
        requester_id=second_requester_user.id,
        assignee_id=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([t_secret, t_public])
    db_session.commit()

    # 1. Requester 2 attempts to search for "Confidential" -> returns empty list (total=0)
    res_req2_q = client.get("/api/v1/tickets?q=Confidential", headers=second_requester_auth_headers)
    assert res_req2_q.status_code == 200
    assert res_req2_q.json()["total"] == 0
    assert len(res_req2_q.json()["items"]) == 0

    # 2. Requester 2 attempts to filter by assignee_id -> returns empty list (total=0)
    res_req2_assignee = client.get(
        f"/api/v1/tickets?assignee_id={agent_user.id}",
        headers=second_requester_auth_headers,
    )
    assert res_req2_assignee.status_code == 200
    assert res_req2_assignee.json()["total"] == 0
    assert len(res_req2_assignee.json()["items"]) == 0

    # 3. Agent searches for "Confidential" -> finds Requester 1's ticket
    res_agent_q = client.get("/api/v1/tickets?q=Confidential", headers=agent_auth_headers)
    assert res_agent_q.status_code == 200
    assert res_agent_q.json()["total"] == 1
    assert res_agent_q.json()["items"][0]["id"] == t_secret.id

    # 4. Agent filters by assignee_id -> finds Requester 1's ticket
    res_agent_assignee = client.get(
        f"/api/v1/tickets?assignee_id={agent_user.id}",
        headers=agent_auth_headers,
    )
    assert res_agent_assignee.status_code == 200
    assert any(t["id"] == t_secret.id for t in res_agent_assignee.json()["items"])
