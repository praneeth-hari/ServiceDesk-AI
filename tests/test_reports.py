from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.history import TicketStatusHistory
from app.models.ticket import Ticket
from app.models.user import User


def test_reports_forbidden_for_requester(
    client: TestClient,
    requester_auth_headers: dict[str, str],
):
    """Test that all report endpoints return 403 Forbidden for requesters."""
    endpoints = [
        "/api/v1/reports/tickets-by-status",
        "/api/v1/reports/overdue",
        "/api/v1/reports/resolution-time",
        "/api/v1/reports/agent-ranking",
        "/api/v1/reports/daily-volume",
        "/api/v1/reports/sla-breach-rate",
        "/api/v1/reports/resolution-time-by-category",
        "/api/v1/reports/agent-workload",
        "/api/v1/reports/tickets-by-category",
    ]
    for url in endpoints:
        res = client.get(url, headers=requester_auth_headers)
        assert res.status_code == 403
        assert res.json()["error"]["message"] == "You do not have permission to access this resource"



def test_daily_volume_validation_errors(
    client: TestClient,
    agent_auth_headers: dict[str, str],
):
    """Test that invalid days query parameter (<1 or >90) returns 422 in standard error format."""
    # days = 0 (min is 1)
    res_zero = client.get("/api/v1/reports/daily-volume?days=0", headers=agent_auth_headers)
    assert res_zero.status_code == 422
    assert "error" in res_zero.json()
    assert "days" in res_zero.json()["error"]["message"]

    # days = 91 (max is 90)
    res_large = client.get("/api/v1/reports/daily-volume?days=91", headers=agent_auth_headers)
    assert res_large.status_code == 422
    assert "error" in res_large.json()
    assert "days" in res_large.json()["error"]["message"]

    # days = not an integer
    res_invalid = client.get("/api/v1/reports/daily-volume?days=invalid", headers=agent_auth_headers)
    assert res_invalid.status_code == 422
    assert "error" in res_invalid.json()


def test_report_tickets_by_status(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    db_session: Session,
    requester_user: User,
):
    """Test tickets-by-status report returns accurate counts per status and priority."""
    now = datetime.now(timezone.utc)

    # Seed tickets
    tickets = [
        Ticket(title="T1", description="D", status=TicketStatus.OPEN, priority=TicketPriority.HIGH, requester_id=requester_user.id, created_at=now, updated_at=now),
        Ticket(title="T2", description="D", status=TicketStatus.OPEN, priority=TicketPriority.HIGH, requester_id=requester_user.id, created_at=now, updated_at=now),
        Ticket(title="T3", description="D", status=TicketStatus.OPEN, priority=TicketPriority.LOW, requester_id=requester_user.id, created_at=now, updated_at=now),
        Ticket(title="T4", description="D", status=TicketStatus.IN_PROGRESS, priority=TicketPriority.URGENT, requester_id=requester_user.id, created_at=now, updated_at=now),
        Ticket(title="T5", description="D", status=TicketStatus.RESOLVED, priority=TicketPriority.MEDIUM, requester_id=requester_user.id, created_at=now, updated_at=now),
    ]
    db_session.add_all(tickets)
    db_session.commit()

    res = client.get("/api/v1/reports/tickets-by-status", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    # Convert to lookup dict: (status, priority) -> count
    counts = {(row["status"], row["priority"]): row["count"] for row in data}
    assert counts.get(("open", "high")) == 2
    assert counts.get(("open", "low")) == 1
    assert counts.get(("in_progress", "urgent")) == 1
    assert counts.get(("resolved", "medium")) == 1


def test_report_overdue(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
):
    """
    Test overdue report:
    - Returns tickets with due_at in the past and status open or in_progress.
    - Includes requester_name and assignee_name.
    - Handles unassigned ticket properly (assignee_id=None, assignee_name=None).
    """
    now = datetime.now(timezone.utc)

    # 1. Assigned overdue ticket (OPEN, past due_at)
    t_assigned = Ticket(
        title="Assigned Overdue",
        description="Desc",
        status=TicketStatus.OPEN,
        priority=TicketPriority.HIGH,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=now - timedelta(days=2),
        created_at=now - timedelta(days=5),
        updated_at=now,
    )
    # 2. Unassigned overdue ticket (IN_PROGRESS, past due_at, assignee_id=None)
    t_unassigned = Ticket(
        title="Unassigned Overdue",
        description="Desc",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.URGENT,
        requester_id=requester_user.id,
        assignee_id=None,
        due_at=now - timedelta(days=1),
        created_at=now - timedelta(days=3),
        updated_at=now,
    )
    # 3. Past due_at but RESOLVED (should NOT be included)
    t_resolved = Ticket(
        title="Resolved Past Due",
        description="Desc",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=now - timedelta(days=3),
        created_at=now - timedelta(days=6),
        updated_at=now,
    )
    # 4. Future due_at (should NOT be included)
    t_future = Ticket(
        title="Future Ticket",
        description="Desc",
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=now + timedelta(days=2),
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([t_assigned, t_unassigned, t_resolved, t_future])
    db_session.commit()

    res = client.get("/api/v1/reports/overdue", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    # Exactly 2 overdue tickets returned
    returned_ids = {row["id"] for row in data}
    assert returned_ids == {t_assigned.id, t_unassigned.id}

    # Verify assigned ticket includes assignee name and requester name
    assigned_row = next(r for r in data if r["id"] == t_assigned.id)
    assert assigned_row["requester_name"] == requester_user.full_name
    assert assigned_row["assignee_id"] == agent_user.id
    assert assigned_row["assignee_name"] == agent_user.full_name

    # Verify unassigned ticket handles null assignee
    unassigned_row = next(r for r in data if r["id"] == t_unassigned.id)
    assert unassigned_row["requester_name"] == requester_user.full_name
    assert unassigned_row["assignee_id"] is None
    assert unassigned_row["assignee_name"] is None


def test_report_resolution_time(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
):
    """
    Test resolution-time report:
    - Calculates average hours from ticket creation to first 'resolved' entry in ticket_status_history.
    - Groups per assignee.
    - Only counts tickets with a resolved history entry.
    """
    now = datetime.now(timezone.utc)

    # Create second agent
    agent2 = User(
        email="agent2_reports@example.com",
        full_name="Second Agent",
        hashed_password="agentpass2",
        role=UserRole.AGENT,
        is_active=True,
    )
    db_session.add(agent2)
    db_session.flush()

    # Agent 1: Ticket 1 created 10 hours ago, resolved 6 hours ago (duration: 4.0 hours)
    t1 = Ticket(
        title="Agent 1 - T1",
        description="Desc",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.MEDIUM,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        created_at=now - timedelta(hours=10),
        updated_at=now,
    )
    # Agent 1: Ticket 2 created 8 hours ago, resolved 2 hours ago (duration: 6.0 hours)
    t2 = Ticket(
        title="Agent 1 - T2",
        description="Desc",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.MEDIUM,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        created_at=now - timedelta(hours=8),
        updated_at=now,
    )
    # Agent 2: Ticket 3 created 4 hours ago, resolved 2 hours ago (duration: 2.0 hours)
    t3 = Ticket(
        title="Agent 2 - T3",
        description="Desc",
        status=TicketStatus.CLOSED,
        priority=TicketPriority.HIGH,
        requester_id=requester_user.id,
        assignee_id=agent2.id,
        created_at=now - timedelta(hours=4),
        updated_at=now,
    )
    # Unresolved ticket: created 5 hours ago, still OPEN (should NOT be counted)
    t_open = Ticket(
        title="Still Open",
        description="Desc",
        status=TicketStatus.OPEN,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        created_at=now - timedelta(hours=5),
        updated_at=now,
    )
    db_session.add_all([t1, t2, t3, t_open])
    db_session.flush()

    # Record status history
    h1 = TicketStatusHistory(ticket_id=t1.id, changed_by_id=agent_user.id, from_status=TicketStatus.IN_PROGRESS, to_status=TicketStatus.RESOLVED, created_at=now - timedelta(hours=6))
    h2 = TicketStatusHistory(ticket_id=t2.id, changed_by_id=agent_user.id, from_status=TicketStatus.IN_PROGRESS, to_status=TicketStatus.RESOLVED, created_at=now - timedelta(hours=2))
    h3 = TicketStatusHistory(ticket_id=t3.id, changed_by_id=agent2.id, from_status=TicketStatus.IN_PROGRESS, to_status=TicketStatus.RESOLVED, created_at=now - timedelta(hours=2))
    # Add a second 'resolved' history row to t1 (to test that the CTE strictly takes MIN/first resolved_at)
    h1_second = TicketStatusHistory(ticket_id=t1.id, changed_by_id=agent_user.id, from_status=TicketStatus.IN_PROGRESS, to_status=TicketStatus.RESOLVED, created_at=now - timedelta(hours=1))
    db_session.add_all([h1, h2, h3, h1_second])
    db_session.commit()

    res = client.get("/api/v1/reports/resolution-time", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    res_by_agent = {row["assignee_id"]: row for row in data}

    # Agent 2: (2.0 hours) / 1 ticket = 2.0
    assert agent2.id in res_by_agent
    assert round(res_by_agent[agent2.id]["avg_resolution_hours"], 1) == 2.0
    assert res_by_agent[agent2.id]["ticket_count"] == 1

    # Agent 1: (4.0 + 6.0) / 2 tickets = 5.0 hours
    assert agent_user.id in res_by_agent
    assert round(res_by_agent[agent_user.id]["avg_resolution_hours"], 1) == 5.0
    assert res_by_agent[agent_user.id]["ticket_count"] == 2


def test_report_agent_ranking_with_ties(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
):
    """
    Test agent-ranking report:
    - Ranks agents by count of tickets resolved using RANK() window function.
    - Verifies tied agents share the same rank.
    """
    now = datetime.now(timezone.utc)

    # Create 2 more agents
    agent_bob = User(email="bob@example.com", full_name="Bob Agent", hashed_password="h", role=UserRole.AGENT, is_active=True)
    agent_charlie = User(email="charlie@example.com", full_name="Charlie Agent", hashed_password="h", role=UserRole.AGENT, is_active=True)
    db_session.add_all([agent_bob, agent_charlie])
    db_session.flush()

    # Agent User resolves 2 tickets
    t1 = Ticket(title="T1", description="D", status=TicketStatus.RESOLVED, priority=TicketPriority.LOW, requester_id=requester_user.id, assignee_id=agent_user.id, created_at=now, updated_at=now)
    t2 = Ticket(title="T2", description="D", status=TicketStatus.CLOSED, priority=TicketPriority.LOW, requester_id=requester_user.id, assignee_id=agent_user.id, created_at=now, updated_at=now)

    # Bob resolves 2 tickets (tied with Agent User!)
    t3 = Ticket(title="T3", description="D", status=TicketStatus.RESOLVED, priority=TicketPriority.LOW, requester_id=requester_user.id, assignee_id=agent_bob.id, created_at=now, updated_at=now)
    t4 = Ticket(title="T4", description="D", status=TicketStatus.RESOLVED, priority=TicketPriority.LOW, requester_id=requester_user.id, assignee_id=agent_bob.id, created_at=now, updated_at=now)

    # Charlie resolves 1 ticket
    t5 = Ticket(title="T5", description="D", status=TicketStatus.RESOLVED, priority=TicketPriority.LOW, requester_id=requester_user.id, assignee_id=agent_charlie.id, created_at=now, updated_at=now)

    db_session.add_all([t1, t2, t3, t4, t5])
    db_session.commit()

    res = client.get("/api/v1/reports/agent-ranking", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    ranking_by_id = {row["agent_id"]: row for row in data}

    # Verify tied agents share rank 1
    assert ranking_by_id[agent_user.id]["rank"] == 1
    assert ranking_by_id[agent_user.id]["resolved_count"] == 2
    assert ranking_by_id[agent_bob.id]["rank"] == 1
    assert ranking_by_id[agent_bob.id]["resolved_count"] == 2

    # Verify Charlie gets rank 3 (RANK skips after ties)
    assert ranking_by_id[agent_charlie.id]["rank"] == 3
    assert ranking_by_id[agent_charlie.id]["resolved_count"] == 1


def test_report_daily_volume(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    db_session: Session,
    requester_user: User,
):
    """
    Test daily-volume report:
    - Returns tickets created per day using a CTE.
    - Excludes tickets outside the lookback window.
    """
    now = datetime.now(timezone.utc)

    # 2 tickets created today
    t1 = Ticket(title="Today 1", description="D", status=TicketStatus.OPEN, priority=TicketPriority.LOW, requester_id=requester_user.id, created_at=now, updated_at=now)
    t2 = Ticket(title="Today 2", description="D", status=TicketStatus.OPEN, priority=TicketPriority.LOW, requester_id=requester_user.id, created_at=now, updated_at=now)

    # 1 ticket created 2 days ago
    t3 = Ticket(title="2 Days Ago", description="D", status=TicketStatus.OPEN, priority=TicketPriority.LOW, requester_id=requester_user.id, created_at=now - timedelta(days=2), updated_at=now)

    # 1 ticket created 100 days ago (outside default 30-day window)
    t4 = Ticket(title="100 Days Ago", description="D", status=TicketStatus.OPEN, priority=TicketPriority.LOW, requester_id=requester_user.id, created_at=now - timedelta(days=100), updated_at=now)

    db_session.add_all([t1, t2, t3, t4])
    db_session.commit()

    res = client.get("/api/v1/reports/daily-volume?days=30", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    # Look up by date
    today_str = now.strftime("%Y-%m-%d")
    two_days_ago_str = (now - timedelta(days=2)).strftime("%Y-%m-%d")

    counts = {row["date"]: row["ticket_count"] for row in data}
    assert counts.get(today_str) == 2
    assert counts.get(two_days_ago_str) == 1

    # Verify 100 days ago is NOT present
    old_date_str = (now - timedelta(days=100)).strftime("%Y-%m-%d")
    assert old_date_str not in counts


def test_reports_unauthenticated_returns_401(client: TestClient):
    """Test that all 9 report endpoints return 401 Unauthorized without auth headers."""
    endpoints = [
        "/api/v1/reports/tickets-by-status",
        "/api/v1/reports/overdue",
        "/api/v1/reports/resolution-time",
        "/api/v1/reports/agent-ranking",
        "/api/v1/reports/daily-volume",
        "/api/v1/reports/sla-breach-rate",
        "/api/v1/reports/resolution-time-by-category",
        "/api/v1/reports/agent-workload",
        "/api/v1/reports/tickets-by-category",
    ]
    for url in endpoints:
        res = client.get(url)
        assert res.status_code == 401
        assert "error" in res.json()


def test_new_reports_empty_data(
    client: TestClient,
    agent_auth_headers: dict[str, str],
):
    """Test that new report endpoints succeed and return empty lists or zeroed workloads when no tickets exist."""
    res_sla = client.get("/api/v1/reports/sla-breach-rate", headers=agent_auth_headers)
    assert res_sla.status_code == 200
    assert isinstance(res_sla.json(), list)

    res_res = client.get("/api/v1/reports/resolution-time-by-category", headers=agent_auth_headers)
    assert res_res.status_code == 200
    assert isinstance(res_res.json(), list)

    res_cat = client.get("/api/v1/reports/tickets-by-category", headers=agent_auth_headers)
    assert res_cat.status_code == 200
    assert isinstance(res_cat.json(), list)

    res_cat_breakdown = client.get("/api/v1/reports/tickets-by-category?breakdown_by_status=true", headers=agent_auth_headers)
    assert res_cat_breakdown.status_code == 200
    assert isinstance(res_cat_breakdown.json(), list)


def test_report_sla_breach_rate(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
):
    """
    Test SLA breach rate report:
    - Urgent: 1 met, 1 breached -> 50.0% breach rate
    - High: 1 breached (unresolved past due) -> 100.0% breach rate
    - Low: 1 met (unresolved on track) -> 0.0% breach rate
    """
    now = datetime.now(timezone.utc)

    # 1. Urgent tickets
    t1 = Ticket(
        title="U1 Met",
        description="D",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.URGENT,
        category=TicketCategory.SOFTWARE,
        requester_id=requester_user.id,
        due_at=now + timedelta(hours=2),
        created_at=now - timedelta(hours=2),
        updated_at=now,
    )
    t2 = Ticket(
        title="U2 Breached",
        description="D",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.URGENT,
        category=TicketCategory.SOFTWARE,
        requester_id=requester_user.id,
        due_at=now - timedelta(hours=1),
        created_at=now - timedelta(hours=4),
        updated_at=now,
    )

    # 2. High ticket: unresolved and past due_at
    t3 = Ticket(
        title="H1 Breached Unresolved",
        description="D",
        status=TicketStatus.OPEN,
        priority=TicketPriority.HIGH,
        category=TicketCategory.NETWORK,
        requester_id=requester_user.id,
        due_at=now - timedelta(hours=2),
        created_at=now - timedelta(hours=5),
        updated_at=now,
    )

    # 3. Low ticket: unresolved, on track
    t4 = Ticket(
        title="L1 Met Unresolved",
        description="D",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.LOW,
        category=TicketCategory.ACCESS,
        requester_id=requester_user.id,
        due_at=now + timedelta(hours=10),
        created_at=now - timedelta(hours=1),
        updated_at=now,
    )

    db_session.add_all([t1, t2, t3, t4])
    db_session.commit()

    # Resolution history:
    # t1 resolved at (now - 1h) which is <= due_at (now + 2h) -> Met
    h1 = TicketStatusHistory(
        ticket_id=t1.id,
        changed_by_id=agent_user.id,
        from_status=TicketStatus.IN_PROGRESS,
        to_status=TicketStatus.RESOLVED,
        created_at=now - timedelta(hours=1),
    )
    # t2 resolved at now which is > due_at (now - 1h) -> Breached
    h2 = TicketStatusHistory(
        ticket_id=t2.id,
        changed_by_id=agent_user.id,
        from_status=TicketStatus.IN_PROGRESS,
        to_status=TicketStatus.RESOLVED,
        created_at=now,
    )
    db_session.add_all([h1, h2])
    db_session.commit()

    res = client.get("/api/v1/reports/sla-breach-rate", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    rates_by_priority = {row["priority"]: row for row in data}
    assert "urgent" in rates_by_priority
    assert rates_by_priority["urgent"]["total_tickets"] == 2
    assert rates_by_priority["urgent"]["met_sla"] == 1
    assert rates_by_priority["urgent"]["breached_sla"] == 1
    assert rates_by_priority["urgent"]["breach_rate"] == 50.0

    assert "high" in rates_by_priority
    assert rates_by_priority["high"]["total_tickets"] == 1
    assert rates_by_priority["high"]["met_sla"] == 0
    assert rates_by_priority["high"]["breached_sla"] == 1
    assert rates_by_priority["high"]["breach_rate"] == 100.0

    assert "low" in rates_by_priority
    assert rates_by_priority["low"]["total_tickets"] == 1
    assert rates_by_priority["low"]["met_sla"] == 1
    assert rates_by_priority["low"]["breached_sla"] == 0
    assert rates_by_priority["low"]["breach_rate"] == 0.0


def test_report_resolution_time_by_category(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
):
    """
    Test resolution time by category report:
    - Only resolved tickets are counted.
    - Software + High: 2 tickets (durations 2h and 4h -> avg 3.0h)
    - Hardware + Low: 1 ticket (duration 5h -> avg 5.0h)
    - Unresolved ticket is excluded.
    """
    now = datetime.now(timezone.utc)

    # 1. Software + High (2h)
    t1 = Ticket(
        title="SW H 1",
        description="D",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.HIGH,
        category=TicketCategory.SOFTWARE,
        requester_id=requester_user.id,
        created_at=now - timedelta(hours=6),
        updated_at=now,
    )
    # 2. Software + High (4h)
    t2 = Ticket(
        title="SW H 2",
        description="D",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.HIGH,
        category=TicketCategory.SOFTWARE,
        requester_id=requester_user.id,
        created_at=now - timedelta(hours=8),
        updated_at=now,
    )
    # 3. Hardware + Low (5h)
    t3 = Ticket(
        title="HW L 1",
        description="D",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.LOW,
        category=TicketCategory.HARDWARE,
        requester_id=requester_user.id,
        created_at=now - timedelta(hours=10),
        updated_at=now,
    )
    # 4. Email + Urgent (Unresolved)
    t4 = Ticket(
        title="Email U Unresolved",
        description="D",
        status=TicketStatus.OPEN,
        priority=TicketPriority.URGENT,
        category=TicketCategory.EMAIL,
        requester_id=requester_user.id,
        created_at=now - timedelta(hours=2),
        updated_at=now,
    )

    db_session.add_all([t1, t2, t3, t4])
    db_session.commit()

    # Add resolution entries
    h1 = TicketStatusHistory(
        ticket_id=t1.id,
        changed_by_id=agent_user.id,
        from_status=TicketStatus.IN_PROGRESS,
        to_status=TicketStatus.RESOLVED,
        created_at=now - timedelta(hours=4),  # 6h - 4h = 2h duration
    )
    h2 = TicketStatusHistory(
        ticket_id=t2.id,
        changed_by_id=agent_user.id,
        from_status=TicketStatus.IN_PROGRESS,
        to_status=TicketStatus.RESOLVED,
        created_at=now - timedelta(hours=4),  # 8h - 4h = 4h duration
    )
    h3 = TicketStatusHistory(
        ticket_id=t3.id,
        changed_by_id=agent_user.id,
        from_status=TicketStatus.IN_PROGRESS,
        to_status=TicketStatus.RESOLVED,
        created_at=now - timedelta(hours=5),  # 10h - 5h = 5h duration
    )
    db_session.add_all([h1, h2, h3])
    db_session.commit()

    res = client.get("/api/v1/reports/resolution-time-by-category", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    lookup = {(row["category"], row["priority"]): row for row in data}
    assert ("software", "high") in lookup
    assert lookup[("software", "high")]["ticket_count"] == 2
    assert round(lookup[("software", "high")]["avg_resolution_hours"], 1) == 3.0

    assert ("hardware", "low") in lookup
    assert lookup[("hardware", "low")]["ticket_count"] == 1
    assert round(lookup[("hardware", "low")]["avg_resolution_hours"], 1) == 5.0

    assert ("email", "urgent") not in lookup


def test_report_agent_workload(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
):
    """
    Test agent workload report:
    - Counts open work (open + in_progress).
    - Counts overdue open work.
    - Counts resolved work (resolved + closed).
    - Includes agents with zero tickets via LEFT JOIN.
    """
    now = datetime.now(timezone.utc)

    # Create a second agent with 0 tickets
    agent_zero = User(
        email="agent_zero@example.com",
        full_name="Agent Zero",
        hashed_password="hash",
        role=UserRole.AGENT,
        is_active=True,
    )
    db_session.add(agent_zero)
    db_session.commit()

    # Assign tickets to agent_user:
    # 1. Open and overdue
    t1 = Ticket(
        title="Open Overdue",
        description="D",
        status=TicketStatus.OPEN,
        priority=TicketPriority.HIGH,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=now - timedelta(hours=2),
        created_at=now - timedelta(hours=5),
        updated_at=now,
    )
    # 2. In progress, not overdue
    t2 = Ticket(
        title="In Progress On Track",
        description="D",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.MEDIUM,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=now + timedelta(hours=5),
        created_at=now - timedelta(hours=1),
        updated_at=now,
    )
    # 3. Resolved
    t3 = Ticket(
        title="Resolved T3",
        description="D",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        created_at=now - timedelta(hours=4),
        updated_at=now,
    )
    # 4. Closed
    t4 = Ticket(
        title="Closed T4",
        description="D",
        status=TicketStatus.CLOSED,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        created_at=now - timedelta(hours=6),
        updated_at=now,
    )

    db_session.add_all([t1, t2, t3, t4])
    db_session.commit()

    res = client.get("/api/v1/reports/agent-workload", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    workload_by_id = {row["agent_id"]: row for row in data}

    # Verify agent_user
    assert agent_user.id in workload_by_id
    u_workload = workload_by_id[agent_user.id]
    assert u_workload["agent_name"] == agent_user.full_name
    assert u_workload["open_tickets"] == 2
    assert u_workload["overdue_tickets"] == 1
    assert u_workload["resolved_tickets"] == 2

    # Verify agent_zero (has 0 tickets, included via LEFT JOIN)
    assert agent_zero.id in workload_by_id
    z_workload = workload_by_id[agent_zero.id]
    assert z_workload["agent_name"] == "Agent Zero"
    assert z_workload["open_tickets"] == 0
    assert z_workload["overdue_tickets"] == 0
    assert z_workload["resolved_tickets"] == 0


def test_report_tickets_by_category(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    db_session: Session,
    requester_user: User,
):
    """
    Test tickets-by-category report:
    - Without breakdown: returns total count per category (status=None).
    - With breakdown: returns count per category and status.
    """
    now = datetime.now(timezone.utc)

    t1 = Ticket(title="T1", description="D", status=TicketStatus.OPEN, priority=TicketPriority.LOW, category=TicketCategory.NETWORK, requester_id=requester_user.id, created_at=now, updated_at=now)
    t2 = Ticket(title="T2", description="D", status=TicketStatus.IN_PROGRESS, priority=TicketPriority.LOW, category=TicketCategory.NETWORK, requester_id=requester_user.id, created_at=now, updated_at=now)
    t3 = Ticket(title="T3", description="D", status=TicketStatus.RESOLVED, priority=TicketPriority.LOW, category=TicketCategory.HARDWARE, requester_id=requester_user.id, created_at=now, updated_at=now)

    db_session.add_all([t1, t2, t3])
    db_session.commit()

    # 1. Without breakdown
    res_no_breakdown = client.get("/api/v1/reports/tickets-by-category", headers=agent_auth_headers)
    assert res_no_breakdown.status_code == 200
    data_no_bd = res_no_breakdown.json()
    cat_counts = {row["category"]: row for row in data_no_bd}
    assert cat_counts["network"]["count"] == 2
    assert cat_counts["network"]["status"] is None
    assert cat_counts["hardware"]["count"] == 1
    assert cat_counts["hardware"]["status"] is None

    # 2. With breakdown
    res_breakdown = client.get("/api/v1/reports/tickets-by-category?breakdown_by_status=true", headers=agent_auth_headers)
    assert res_breakdown.status_code == 200
    data_bd = res_breakdown.json()
    bd_counts = {(row["category"], row["status"]): row["count"] for row in data_bd}
    assert bd_counts.get(("network", "open")) == 1
    assert bd_counts.get(("network", "in_progress")) == 1
    assert bd_counts.get(("hardware", "resolved")) == 1


def test_reports_with_waiting_on_requester_and_paused_sla(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
):
    """
    Test that reports properly handle waiting_on_requester status:
    - tickets-by-status includes waiting_on_requester
    - overdue excludes paused tickets even if due_at is in the past
    - sla-breach-rate treats waiting_on_requester as unresolved but not overdue-while-paused (met_sla)
    - agent-workload counts waiting_on_requester as open work but not overdue
    """
    now = datetime.now(timezone.utc)

    # Ticket in waiting_on_requester with due_at in past and sla_paused_at set
    t_paused = Ticket(
        title="Paused Ticket",
        description="Waiting on requester",
        status=TicketStatus.WAITING_ON_REQUESTER,
        priority=TicketPriority.HIGH,
        category=TicketCategory.SOFTWARE,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=now - timedelta(hours=2),
        sla_paused_at=now - timedelta(hours=3),
        created_at=now - timedelta(hours=10),
        updated_at=now,
    )
    db_session.add(t_paused)
    db_session.commit()

    # 1. tickets-by-status includes waiting_on_requester
    res_status = client.get("/api/v1/reports/tickets-by-status", headers=agent_auth_headers)
    assert res_status.status_code == 200
    status_counts = {(r["status"], r["priority"]): r["count"] for r in res_status.json()}
    assert status_counts.get(("waiting_on_requester", "high")) == 1

    # 2. overdue report excludes paused tickets
    res_overdue = client.get("/api/v1/reports/overdue", headers=agent_auth_headers)
    assert res_overdue.status_code == 200
    overdue_ids = [r["id"] for r in res_overdue.json()]
    assert t_paused.id not in overdue_ids

    # 3. sla-breach-rate treats waiting_on_requester as unresolved but not breached
    res_sla = client.get("/api/v1/reports/sla-breach-rate", headers=agent_auth_headers)
    assert res_sla.status_code == 200
    sla_map = {r["priority"]: r for r in res_sla.json()}
    assert "high" in sla_map
    assert sla_map["high"]["total_tickets"] == 1
    assert sla_map["high"]["breached_sla"] == 0
    assert sla_map["high"]["met_sla"] == 1
    assert float(sla_map["high"]["breach_rate"]) == 0.0

    # 4. agent-workload counts waiting_on_requester as open work, but not overdue
    res_workload = client.get("/api/v1/reports/agent-workload", headers=agent_auth_headers)
    assert res_workload.status_code == 200
    workload_map = {r["agent_id"]: r for r in res_workload.json()}
    assert agent_user.id in workload_map
    assert workload_map[agent_user.id]["open_tickets"] == 1
    assert workload_map[agent_user.id]["overdue_tickets"] == 0


