from datetime import datetime, timedelta, timezone
import os
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.history import TicketStatusHistory
from app.models.ticket import Ticket
from app.models.user import User
from app.services.reports import (
    get_agent_ranking,
    get_agent_workload,
    get_daily_volume,
    get_overdue_tickets,
    get_resolution_time,
    get_resolution_time_by_category,
    get_sla_breach_rate,
    get_tickets_by_category,
    get_tickets_by_status,
)

TEST_MYSQL_URL = os.getenv("TEST_MYSQL_URL")

pytestmark = [
    pytest.mark.mysql,
    pytest.mark.skipif(
        not TEST_MYSQL_URL,
        reason="TEST_MYSQL_URL environment variable is not set; skipping MySQL integration tests",
    ),
]


@pytest.fixture
def mysql_session():
    """Provide a transactional database session against the real MySQL instance."""
    engine = sa.create_engine(TEST_MYSQL_URL)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
    engine.dispose()


def test_mysql_all_reports(mysql_session: Session):
    """
    Integration test running all 9 reports against real MySQL 8.
    Verifies MySQL TIMESTAMPDIFF, RANK() OVER, CTEs, and JOINs execute flawlessly.
    """
    now = datetime.now(timezone.utc)

    # 1. Seed users
    agent1 = User(
        email="mysql_agent1@example.com",
        full_name="MySQL Agent 1",
        hashed_password="hash",
        role=UserRole.AGENT,
        is_active=True,
    )
    agent2 = User(
        email="mysql_agent2@example.com",
        full_name="MySQL Agent 2",
        hashed_password="hash",
        role=UserRole.AGENT,
        is_active=True,
    )
    agent3 = User(
        email="mysql_agent3@example.com",
        full_name="MySQL Agent 3 (Idle)",
        hashed_password="hash",
        role=UserRole.AGENT,
        is_active=True,
    )
    requester = User(
        email="mysql_req@example.com",
        full_name="MySQL Requester",
        hashed_password="hash",
        role=UserRole.REQUESTER,
        is_active=True,
    )
    mysql_session.add_all([agent1, agent2, agent3, requester])
    mysql_session.flush()

    # 2. Seed tickets
    # Overdue assigned
    t1 = Ticket(
        title="MySQL Overdue Assigned",
        description="Desc",
        status=TicketStatus.OPEN,
        priority=TicketPriority.HIGH,
        category=TicketCategory.NETWORK,
        requester_id=requester.id,
        assignee_id=agent1.id,
        due_at=now - timedelta(days=2),
        created_at=now - timedelta(days=5),
        updated_at=now,
    )
    # Overdue unassigned
    t2 = Ticket(
        title="MySQL Overdue Unassigned",
        description="Desc",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.MEDIUM,
        category=TicketCategory.SOFTWARE,
        requester_id=requester.id,
        assignee_id=None,
        due_at=now - timedelta(days=1),
        created_at=now - timedelta(days=3),
        updated_at=now,
    )
    # Resolved ticket for agent 1 (created 6h ago, resolved 2h ago -> 4h duration)
    t3 = Ticket(
        title="MySQL Resolved T3",
        description="Desc",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.LOW,
        category=TicketCategory.HARDWARE,
        requester_id=requester.id,
        assignee_id=agent1.id,
        due_at=now + timedelta(days=1),
        created_at=now - timedelta(hours=6),
        updated_at=now,
    )
    # Resolved ticket for agent 2 (created 3h ago, resolved 1h ago -> 2h duration)
    t4 = Ticket(
        title="MySQL Resolved T4",
        description="Desc",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.URGENT,
        category=TicketCategory.SOFTWARE,
        requester_id=requester.id,
        assignee_id=agent2.id,
        due_at=now + timedelta(days=1),
        created_at=now - timedelta(hours=3),
        updated_at=now,
    )
    mysql_session.add_all([t1, t2, t3, t4])
    mysql_session.flush()

    # Seed history for resolved tickets
    h1 = TicketStatusHistory(
        ticket_id=t3.id,
        changed_by_id=agent1.id,
        from_status=TicketStatus.IN_PROGRESS,
        to_status=TicketStatus.RESOLVED,
        created_at=now - timedelta(hours=2),
    )
    h2 = TicketStatusHistory(
        ticket_id=t4.id,
        changed_by_id=agent2.id,
        from_status=TicketStatus.IN_PROGRESS,
        to_status=TicketStatus.RESOLVED,
        created_at=now - timedelta(hours=1),
    )
    mysql_session.add_all([h1, h2])
    mysql_session.flush()

    # 1. Report: tickets by status
    status_report = get_tickets_by_status(mysql_session)
    assert len(status_report) >= 2

    # 2. Report: overdue tickets
    overdue_report = get_overdue_tickets(mysql_session, current_time=now)
    overdue_ids = {r["id"] for r in overdue_report}
    assert t1.id in overdue_ids
    assert t2.id in overdue_ids

    # Check assigned vs unassigned in MySQL
    assigned_row = next(r for r in overdue_report if r["id"] == t1.id)
    assert assigned_row["assignee_name"] == agent1.full_name
    unassigned_row = next(r for r in overdue_report if r["id"] == t2.id)
    assert unassigned_row["assignee_name"] is None

    # 3. Report: resolution time (verifying MySQL TIMESTAMPDIFF)
    res_time_report = get_resolution_time(mysql_session)
    agent_res_map = {r["assignee_id"]: r for r in res_time_report}
    assert agent1.id in agent_res_map
    assert round(float(agent_res_map[agent1.id]["avg_resolution_hours"]), 1) == 4.0
    assert agent2.id in agent_res_map
    assert round(float(agent_res_map[agent2.id]["avg_resolution_hours"]), 1) == 2.0

    # 4. Report: agent ranking (verifying MySQL RANK() OVER window function)
    ranking_report = get_agent_ranking(mysql_session)
    assert len(ranking_report) >= 2
    # Both agents resolved 1 ticket, so they share rank 1 in MySQL!
    r_map = {r["agent_id"]: r for r in ranking_report}
    assert r_map[agent1.id]["rank"] == 1
    assert r_map[agent2.id]["rank"] == 1

    # 5. Report: daily volume
    volume_report = get_daily_volume(mysql_session, days=30, current_time=now)
    assert len(volume_report) >= 1

    # 6. Report: sla-breach-rate (verifying MySQL breach rate and compliance calculations)
    breach_report = get_sla_breach_rate(mysql_session, current_time=now)
    breach_map = {r["priority"]: r for r in breach_report}
    assert "high" in breach_map
    assert breach_map["high"]["breached_sla"] == 1
    assert float(breach_map["high"]["breach_rate"]) == 100.0
    assert "low" in breach_map
    assert breach_map["low"]["met_sla"] == 1
    assert float(breach_map["low"]["breach_rate"]) == 0.0

    # 7. Report: resolution-time-by-category (verifying MySQL TIMESTAMPDIFF grouped by category)
    res_cat_report = get_resolution_time_by_category(mysql_session)
    res_cat_map = {(r["category"], r["priority"]): r for r in res_cat_report}
    assert ("hardware", "low") in res_cat_map
    assert round(float(res_cat_map[("hardware", "low")]["avg_resolution_hours"]), 1) == 4.0
    assert ("software", "urgent") in res_cat_map
    assert round(float(res_cat_map[("software", "urgent")]["avg_resolution_hours"]), 1) == 2.0

    # 8. Report: agent-workload (verifying MySQL CTE and LEFT JOIN for 0-ticket agent)
    workload_report = get_agent_workload(mysql_session, current_time=now)
    workload_map = {r["agent_id"]: r for r in workload_report}
    assert agent1.id in workload_map
    assert workload_map[agent1.id]["open_tickets"] == 1
    assert workload_map[agent1.id]["overdue_tickets"] == 1
    assert workload_map[agent1.id]["resolved_tickets"] == 1
    assert agent3.id in workload_map
    assert workload_map[agent3.id]["open_tickets"] == 0
    assert workload_map[agent3.id]["overdue_tickets"] == 0
    assert workload_map[agent3.id]["resolved_tickets"] == 0

    # 9. Report: tickets-by-category (with and without breakdown)
    cat_report = get_tickets_by_category(mysql_session, breakdown_by_status=False)
    assert len(cat_report) >= 3
    cat_bd_report = get_tickets_by_category(mysql_session, breakdown_by_status=True)
    assert len(cat_bd_report) >= 4


def test_mysql_waiting_on_requester_and_paused_sla(mysql_session: Session):
    """
    Integration test against MySQL 8 covering:
    - tickets_by_status includes waiting_on_requester.
    - overdue report excludes tickets in waiting_on_requester with sla_paused_at.
    - sla_breach_rate treats waiting_on_requester as unresolved but not breached while paused.
    - agent_workload counts waiting_on_requester as open work but not overdue.
    """
    now = datetime.now(timezone.utc)

    agent = User(
        email="mysql_wait_agent@example.com",
        full_name="MySQL Waiting Agent",
        hashed_password="hash",
        role=UserRole.AGENT,
        is_active=True,
    )
    requester = User(
        email="mysql_wait_req@example.com",
        full_name="MySQL Waiting Req",
        hashed_password="hash",
        role=UserRole.REQUESTER,
        is_active=True,
    )
    mysql_session.add_all([agent, requester])
    mysql_session.flush()

    # Ticket in waiting_on_requester with past due_at but sla_paused_at set
    t_paused = Ticket(
        title="MySQL Paused Ticket",
        description="Waiting for requester response",
        status=TicketStatus.WAITING_ON_REQUESTER,
        priority=TicketPriority.HIGH,
        category=TicketCategory.SOFTWARE,
        requester_id=requester.id,
        assignee_id=agent.id,
        due_at=now - timedelta(hours=2),
        sla_paused_at=now - timedelta(hours=3),
        created_at=now - timedelta(hours=8),
        updated_at=now,
    )
    mysql_session.add(t_paused)
    mysql_session.flush()

    # 1. tickets_by_status
    status_report = get_tickets_by_status(mysql_session)
    status_counts = {(r["status"], r["priority"]): r["count"] for r in status_report}
    assert ("waiting_on_requester", "high") in status_counts

    # 2. overdue report excludes paused ticket
    overdue_report = get_overdue_tickets(mysql_session, current_time=now)
    overdue_ids = {r["id"] for r in overdue_report}
    assert t_paused.id not in overdue_ids

    # 3. sla_breach_rate treats waiting_on_requester as unresolved but not breached
    breach_report = get_sla_breach_rate(mysql_session, current_time=now)
    breach_map = {r["priority"]: r for r in breach_report}
    assert "high" in breach_map
    assert breach_map["high"]["met_sla"] >= 1

    # 4. agent_workload counts waiting_on_requester as open work, not overdue
    workload_report = get_agent_workload(mysql_session, current_time=now)
    workload_map = {r["agent_id"]: r for r in workload_report}
    assert agent.id in workload_map
    assert workload_map[agent.id]["open_tickets"] == 1
    assert workload_map[agent.id]["overdue_tickets"] == 0


def test_mysql_ai_triage_and_embeddings(mysql_session: Session):
    """
    Integration test verifying TicketEmbedding binary storage, CASCADE deletion,
    and triage similarity calculations against real MySQL 8.
    """
    now = datetime.now(timezone.utc)

    user = User(
        email="mysql_ai_user@example.com",
        full_name="MySQL AI User",
        hashed_password="hash",
        role=UserRole.AGENT,
        is_active=True,
    )
    mysql_session.add(user)
    mysql_session.flush()

    ticket = Ticket(
        title="MySQL WiFi Outage",
        description="WiFi connectivity failure on 3rd floor switch",
        status=TicketStatus.OPEN,
        category=TicketCategory.NETWORK,
        priority=TicketPriority.HIGH,
        requester_id=user.id,
        created_at=now,
        updated_at=now,
    )
    mysql_session.add(ticket)
    mysql_session.flush()

    from app.ai.embedder import get_embedder
    from app.services.triage import sync_ticket_embedding, find_similar
    from app.models.embedding import TicketEmbedding

    # 1. Sync embedding into MySQL 8
    sync_ticket_embedding(mysql_session, ticket)
    mysql_session.flush()

    emb = mysql_session.get(TicketEmbedding, ticket.id)
    assert emb is not None
    active_embedder = get_embedder()
    assert emb.model_name == active_embedder.name
    assert emb.dim == active_embedder.dim
    assert len(emb.vector) == active_embedder.dim * 4  # float32 = 4 bytes per dim

    # 2. Similarity search in MySQL 8
    similar = find_similar(
        db=mysql_session,
        text="WiFi network connection broken",
        current_user=user,
        limit=5,
    )
    assert len(similar) >= 1
    assert similar[0]["id"] == ticket.id
    assert similar[0]["similarity"] > 0.0

    # 3. Test ON DELETE CASCADE from Ticket to TicketEmbedding in MySQL 8
    mysql_session.delete(ticket)
    mysql_session.flush()
    emb_after_del = mysql_session.get(TicketEmbedding, ticket.id)
    assert emb_after_del is None


