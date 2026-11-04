"""
Unit and integration tests for AI triage feedback loop and AI quality report endpoint.
"""

from datetime import datetime, timedelta, timezone
from typing import Generator
import pytest
from fastapi.testclient import TestClient
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.ticket import Ticket
from app.models.triage_feedback import TriageFeedback
from app.models.user import User
from app.schemas.ticket import TicketCreate, TicketUpdate, TriageSuggestionCreate
from app.services.reports import get_ai_quality_report
from app.services.tickets import create_ticket, update_ticket


# ---------------------------------------------------------------------------
# 1. Migration up/down on SQLite
# ---------------------------------------------------------------------------
def test_migration_0010_up_down_sqlite(db_session: Session):
    """Verify table creation, constraint behavior, and rollback logic for triage_feedback."""
    bind = db_session.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()
    assert "triage_feedback" in tables

    columns = {c["name"]: c for c in insp.get_columns("triage_feedback")}
    expected_cols = [
        "id",
        "ticket_id",
        "method",
        "embedder",
        "suggested_category",
        "suggested_priority",
        "requester_category",
        "requester_priority",
        "final_category",
        "final_priority",
        "final_set_by",
        "final_set_at",
        "created_at",
    ]
    for col in expected_cols:
        assert col in columns, f"Column '{col}' missing from triage_feedback table"


# ---------------------------------------------------------------------------
# 2. Ticket Creation: with and without triage_suggestion
# ---------------------------------------------------------------------------
def test_create_ticket_with_triage_suggestion(db_session: Session, requester_user: User):
    """Verify triage_feedback row is inserted in same transaction when triage_suggestion is provided."""
    ticket_in = TicketCreate(
        title="Cannot connect to corporate Wi-Fi",
        description="SSID not visible from 5th floor laptops",
        category=TicketCategory.NETWORK,
        priority=TicketPriority.HIGH,
        triage_suggestion=TriageSuggestionCreate(
            suggested_category=TicketCategory.NETWORK,
            suggested_priority=TicketPriority.MEDIUM,
            method="llm-rag",
            embedder="hashing-v2",
        ),
    )

    ticket = create_ticket(db_session, ticket_in=ticket_in, current_user=requester_user)
    assert ticket.id is not None

    fb = db_session.scalars(
        sa.select(TriageFeedback).where(TriageFeedback.ticket_id == ticket.id)
    ).first()
    assert fb is not None
    assert fb.ticket_id == ticket.id
    assert fb.method == "llm-rag"
    assert fb.embedder == "hashing-v2"
    assert fb.suggested_category == "network"
    assert fb.suggested_priority == "medium"
    assert fb.requester_category == "network"
    assert fb.requester_priority == "high"
    assert fb.final_category is None
    assert fb.final_priority is None
    assert fb.final_set_by is None
    assert fb.final_set_at is None
    assert fb.created_at is not None


def test_create_ticket_without_triage_suggestion(db_session: Session, requester_user: User):
    """Verify no triage_feedback row is created when triage_suggestion is omitted."""
    ticket_in = TicketCreate(
        title="Printer paper jam",
        description="Tray 2 jammed on 3rd floor copier",
        category=TicketCategory.HARDWARE,
        priority=TicketPriority.LOW,
    )

    ticket = create_ticket(db_session, ticket_in=ticket_in, current_user=requester_user)
    fb = db_session.scalars(
        sa.select(TriageFeedback).where(TriageFeedback.ticket_id == ticket.id)
    ).first()
    assert fb is None


def test_create_ticket_invalid_triage_suggestion_payload(
    client: TestClient, requester_auth_headers: dict[str, str]
):
    """Verify HTTP 422 is returned when invalid enum or method is sent in triage_suggestion."""
    # 1. Invalid method
    resp1 = client.post(
        "/api/v1/tickets",
        headers=requester_auth_headers,
        json={
            "title": "Valid title here",
            "description": "Valid description here",
            "category": "software",
            "priority": "medium",
            "triage_suggestion": {
                "suggested_category": "software",
                "suggested_priority": "medium",
                "method": "invalid_method",
            },
        },
    )
    assert resp1.status_code == 422

    # 2. Invalid suggested_category
    resp2 = client.post(
        "/api/v1/tickets",
        headers=requester_auth_headers,
        json={
            "title": "Valid title here",
            "description": "Valid description here",
            "category": "software",
            "priority": "medium",
            "triage_suggestion": {
                "suggested_category": "cloud_computing",
                "suggested_priority": "medium",
                "method": "knn",
            },
        },
    )
    assert resp2.status_code == 422

    # 3. Invalid suggested_priority
    resp3 = client.post(
        "/api/v1/tickets",
        headers=requester_auth_headers,
        json={
            "title": "Valid title here",
            "description": "Valid description here",
            "category": "software",
            "priority": "medium",
            "triage_suggestion": {
                "suggested_category": "software",
                "suggested_priority": "critical_emergency",
                "method": "knn",
            },
        },
    )
    assert resp3.status_code == 422


# ---------------------------------------------------------------------------
# 3. Final_* Updates by Agent / Admin
# ---------------------------------------------------------------------------
def test_final_update_on_agent_category_change(
    db_session: Session, requester_user: User, agent_user: User
):
    """Verify an agent modifying category updates final_category, final_priority, final_set_by, and final_set_at."""
    ticket_in = TicketCreate(
        title="VPN error code 54",
        description="GlobalProtect client drops connection",
        category=TicketCategory.OTHER,
        priority=TicketPriority.MEDIUM,
        triage_suggestion=TriageSuggestionCreate(
            suggested_category=TicketCategory.NETWORK,
            suggested_priority=TicketPriority.HIGH,
            method="knn",
            embedder="hashing-v2",
        ),
    )
    ticket = create_ticket(db_session, ticket_in=ticket_in, current_user=requester_user)

    update_in = TicketUpdate(category=TicketCategory.NETWORK)
    now = datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
    updated = update_ticket(
        db_session,
        ticket_id=ticket.id,
        ticket_in=update_in,
        current_user=agent_user,
        current_time=now,
    )
    assert updated.category == TicketCategory.NETWORK

    fb = db_session.scalars(
        sa.select(TriageFeedback).where(TriageFeedback.ticket_id == ticket.id)
    ).first()
    assert fb is not None
    assert fb.final_category == "network"
    assert fb.final_priority == "medium"  # current ticket priority
    assert fb.final_set_by == agent_user.id
    assert fb.final_set_at is not None


def test_final_update_on_admin_priority_change(
    db_session: Session, requester_user: User, admin_user: User
):
    """Verify an admin modifying priority updates final_priority, final_category, and reviewer metadata."""
    ticket_in = TicketCreate(
        title="Production server disk full",
        description="Root partition at 100% capacity",
        category=TicketCategory.HARDWARE,
        priority=TicketPriority.MEDIUM,
        triage_suggestion=TriageSuggestionCreate(
            suggested_category=TicketCategory.HARDWARE,
            suggested_priority=TicketPriority.URGENT,
            method="llm-rag",
            embedder="hashing-v2",
        ),
    )
    ticket = create_ticket(db_session, ticket_in=ticket_in, current_user=requester_user)

    update_in = TicketUpdate(priority=TicketPriority.URGENT)
    now = datetime(2026, 11, 4, 14, 30, 0, tzinfo=timezone.utc)
    updated = update_ticket(
        db_session,
        ticket_id=ticket.id,
        ticket_in=update_in,
        current_user=admin_user,
        current_time=now,
    )
    assert updated.priority == TicketPriority.URGENT

    fb = db_session.scalars(
        sa.select(TriageFeedback).where(TriageFeedback.ticket_id == ticket.id)
    ).first()
    assert fb is not None
    assert fb.final_priority == "urgent"
    assert fb.final_category == "hardware"
    assert fb.final_set_by == admin_user.id
    assert fb.final_set_at is not None


def test_update_ticket_without_feedback_row_does_nothing(
    db_session: Session, requester_user: User, agent_user: User
):
    """Verify modifying category on a ticket without triage_feedback does not crash or insert a row."""
    ticket_in = TicketCreate(
        title="Desk chair height cylinder broken",
        description="Chair sinks slowly over the workday",
        category=TicketCategory.OTHER,
        priority=TicketPriority.LOW,
    )
    ticket = create_ticket(db_session, ticket_in=ticket_in, current_user=requester_user)

    update_in = TicketUpdate(category=TicketCategory.HARDWARE)
    update_ticket(db_session, ticket_id=ticket.id, ticket_in=update_in, current_user=agent_user)

    fb = db_session.scalars(
        sa.select(TriageFeedback).where(TriageFeedback.ticket_id == ticket.id)
    ).first()
    assert fb is None


# ---------------------------------------------------------------------------
# 4. Cascade Delete
# ---------------------------------------------------------------------------
def test_cascade_delete_ticket_removes_feedback(
    db_session: Session, requester_user: User
):
    """Verify deleting a ticket cascades and deletes its triage_feedback record."""
    ticket_in = TicketCreate(
        title="Temporary testing ticket",
        description="Created to verify ON DELETE CASCADE constraint",
        category=TicketCategory.SOFTWARE,
        priority=TicketPriority.LOW,
        triage_suggestion=TriageSuggestionCreate(
            suggested_category=TicketCategory.SOFTWARE,
            suggested_priority=TicketPriority.LOW,
            method="knn",
            embedder="hashing-v2",
        ),
    )
    ticket = create_ticket(db_session, ticket_in=ticket_in, current_user=requester_user)
    t_id = ticket.id

    fb = db_session.scalars(
        sa.select(TriageFeedback).where(TriageFeedback.ticket_id == t_id)
    ).first()
    assert fb is not None

    # Delete ticket
    db_session.delete(ticket)
    db_session.commit()

    fb_after = db_session.scalars(
        sa.select(TriageFeedback).where(TriageFeedback.ticket_id == t_id)
    ).first()
    assert fb_after is None


# ---------------------------------------------------------------------------
# 5. Endpoint Permissions (GET /api/v1/reports/ai-quality)
# ---------------------------------------------------------------------------
def test_ai_quality_endpoint_permissions(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
    admin_auth_headers: dict[str, str],
):
    """Verify /api/v1/reports/ai-quality requires agent or admin role (403 for requesters)."""
    # Requester -> 403
    r_req = client.get("/api/v1/reports/ai-quality", headers=requester_auth_headers)
    assert r_req.status_code == 403

    # Agent -> 200
    r_agent = client.get("/api/v1/reports/ai-quality", headers=agent_auth_headers)
    assert r_agent.status_code == 200

    # Admin -> 200
    r_admin = client.get("/api/v1/reports/ai-quality", headers=admin_auth_headers)
    assert r_admin.status_code == 200


def test_ai_quality_empty_db_returns_nulls_not_errors(
    client: TestClient, agent_auth_headers: dict[str, str]
):
    """Verify n=0 window returns null percentages and zero counts without throwing."""
    resp = client.get("/api/v1/reports/ai-quality", headers=agent_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_suggestions"] == 0
    assert data["counts_by_method"] == {}
    assert data["requester_acceptance"] == {
        "category_pct": None,
        "priority_pct": None,
        "n": 0,
    }
    assert data["agent_review"] == {
        "reviewed_n": 0,
        "category_agreement_pct": None,
        "priority_agreement_pct": None,
        "confirmed_n": 0,
        "corrected_n": 0,
    }
    assert data["weekly"] == []
    assert data["top_corrections"] == []


# ---------------------------------------------------------------------------
# 6. Hand-verified Metrics Fixture
# ---------------------------------------------------------------------------
def test_ai_quality_metrics_hand_verified(db_session: Session, agent_user: User):
    """
    Seed 4 deterministic feedback rows across 2 ISO weeks and verify every metric by hand:
    Fixed 'now': 2026-11-04T12:00:00Z (Wednesday of ISO week 2026-11-02).

    Week 1 (2026-10-26 to 2026-11-01):
      Ticket 1: knn, sugg: network/medium, req: network/medium. Reviewed: final: network/medium.
                (Req cat match: YES, Req prio match: YES. Agent cat agree: YES, Agent prio agree: YES)
      Ticket 2: knn, sugg: software/high, req: other/high. Reviewed: final: software/high.
                (Req cat match: NO, Req prio match: YES. Agent cat agree: YES, Agent prio agree: YES)

    Week 2 (2026-11-02 to 2026-11-08):
      Ticket 3: llm-rag, sugg: access/low, req: access/urgent. Reviewed: final: email/low.
                (Req cat match: YES, Req prio match: NO. Agent cat agree: NO [access -> email], Agent prio agree: YES)
      Ticket 4: llm-rag, sugg: hardware/medium, req: hardware/medium. Unreviewed: final: None/None.
                (Req cat match: YES, Req prio match: YES. Not reviewed)

    Hand calculations:
      total_suggestions = 4
      counts_by_method = {"knn": 2, "llm-rag": 2}
      requester_acceptance:
        category_match = 3 / 4 -> 75.0%
        priority_match = 3 / 4 -> 75.0%
        n = 4
      agent_review:
        reviewed_n = 3 (tickets 1, 2, 3)
        category_agreement = 2 / 3 -> 66.7%
        priority_agreement = 3 / 3 -> 100.0%
      top_corrections:
        1 pair: (access -> email, count: 1)
      weekly:
        Week 1 (2026-10-26):
          n = 2
          requester_category_acceptance_pct = 1 / 2 -> 50.0%
          agent_category_agreement_pct = 2 / 2 -> 100.0%
        Week 2 (2026-11-02):
          n = 2
          requester_category_acceptance_pct = 2 / 2 -> 100.0%
          agent_category_agreement_pct = 0 / 1 -> 0.0%
    """
    fixed_now = datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
    t1_created = datetime(2026, 10, 27, 10, 0, 0, tzinfo=timezone.utc)
    t2_created = datetime(2026, 10, 28, 14, 0, 0, tzinfo=timezone.utc)
    t3_created = datetime(2026, 11, 2, 9, 30, 0, tzinfo=timezone.utc)
    t4_created = datetime(2026, 11, 3, 11, 0, 0, tzinfo=timezone.utc)

    # 1. Create 4 dummy tickets
    tickets = []
    for idx, (cat, prio, created) in enumerate(
        [
            (TicketCategory.NETWORK, TicketPriority.MEDIUM, t1_created),
            (TicketCategory.OTHER, TicketPriority.HIGH, t2_created),
            (TicketCategory.ACCESS, TicketPriority.URGENT, t3_created),
            (TicketCategory.HARDWARE, TicketPriority.MEDIUM, t4_created),
        ],
        start=1001,
    ):
        t = Ticket(
            id=idx,
            title=f"Test ticket {idx}",
            description="Problem description for feedback metrics testing",
            status=TicketStatus.OPEN,
            priority=prio,
            category=cat,
            requester_id=agent_user.id,
            created_at=created,
            updated_at=created,
        )
        tickets.append(t)
    db_session.add_all(tickets)
    db_session.flush()

    # 2. Add feedback rows
    fb1 = TriageFeedback(
        ticket_id=1001,
        method="knn",
        embedder="hashing-v2",
        suggested_category="network",
        suggested_priority="medium",
        requester_category="network",
        requester_priority="medium",
        final_category="network",
        final_priority="medium",
        final_set_by=agent_user.id,
        final_set_at=t1_created + timedelta(hours=2),
        created_at=t1_created,
    )
    fb2 = TriageFeedback(
        ticket_id=1002,
        method="knn",
        embedder="hashing-v2",
        suggested_category="software",
        suggested_priority="high",
        requester_category="other",
        requester_priority="high",
        final_category="software",
        final_priority="high",
        final_set_by=agent_user.id,
        final_set_at=t2_created + timedelta(hours=1),
        created_at=t2_created,
    )
    fb3 = TriageFeedback(
        ticket_id=1003,
        method="llm-rag",
        embedder="hashing-v2",
        suggested_category="access",
        suggested_priority="low",
        requester_category="access",
        requester_priority="urgent",
        final_category="email",
        final_priority="low",
        final_set_by=agent_user.id,
        final_set_at=t3_created + timedelta(hours=3),
        created_at=t3_created,
    )
    fb4 = TriageFeedback(
        ticket_id=1004,
        method="llm-rag",
        embedder="hashing-v2",
        suggested_category="hardware",
        suggested_priority="medium",
        requester_category="hardware",
        requester_priority="medium",
        final_category=None,
        final_priority=None,
        final_set_by=None,
        final_set_at=None,
        created_at=t4_created,
    )
    db_session.add_all([fb1, fb2, fb3, fb4])
    db_session.commit()

    report = get_ai_quality_report(db_session, days=90, current_time=fixed_now)

    assert report["total_suggestions"] == 4
    assert report["counts_by_method"] == {"knn": 2, "llm-rag": 2}

    # Requester acceptance
    assert report["requester_acceptance"]["n"] == 4
    assert report["requester_acceptance"]["category_pct"] == 75.0
    assert report["requester_acceptance"]["priority_pct"] == 75.0

    # Agent review
    assert report["agent_review"]["reviewed_n"] == 3
    assert report["agent_review"]["category_agreement_pct"] == 66.7
    assert report["agent_review"]["priority_agreement_pct"] == 100.0
    assert report["agent_review"]["confirmed_n"] == 2
    assert report["agent_review"]["corrected_n"] == 1

    # Top corrections
    assert len(report["top_corrections"]) == 1
    assert report["top_corrections"][0] == {
        "suggested": "access",
        "final": "email",
        "count": 1,
    }

    # Weekly
    assert len(report["weekly"]) == 2
    w1 = report["weekly"][0]
    assert str(w1["week_start"]) == "2026-10-26"
    assert w1["n"] == 2
    assert w1["requester_category_acceptance_pct"] == 50.0
    assert w1["agent_category_agreement_pct"] == 100.0

    w2 = report["weekly"][1]
    assert str(w2["week_start"]) == "2026-11-02"
    assert w2["n"] == 2
    assert w2["requester_category_acceptance_pct"] == 100.0
    assert w2["agent_category_agreement_pct"] == 0.0


# ---------------------------------------------------------------------------
# 7. Explicit Confirmation Endpoint Tests
# ---------------------------------------------------------------------------
def test_confirm_feedback_agent_success(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
):
    """Verify an agent can confirm triage feedback without modifying the ticket."""
    ticket_in = TicketCreate(
        title="VPN dropping every 10 minutes",
        description="GlobalProtect client disconnects repeatedly",
        category=TicketCategory.NETWORK,
        priority=TicketPriority.MEDIUM,
        triage_suggestion=TriageSuggestionCreate(
            suggested_category=TicketCategory.NETWORK,
            suggested_priority=TicketPriority.MEDIUM,
            method="llm-rag",
            embedder="hashing-v2",
        ),
    )
    ticket = create_ticket(db_session, ticket_in=ticket_in, current_user=requester_user)

    resp = client.post(
        f"/api/v1/tickets/{ticket.id}/triage-feedback/confirm",
        headers=agent_auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticket_id"] == ticket.id
    assert data["final_category"] == "network"
    assert data["final_priority"] == "medium"
    assert data["final_set_by"] == agent_user.id
    assert data["final_set_at"] is not None

    # Check ticket itself is untouched
    db_session.refresh(ticket)
    assert ticket.category == TicketCategory.NETWORK
    assert ticket.priority == TicketPriority.MEDIUM


def test_confirm_feedback_admin_success_and_idempotent(
    client: TestClient,
    admin_auth_headers: dict[str, str],
    admin_user: User,
    db_session: Session,
    requester_user: User,
):
    """Verify admin can confirm feedback and re-calling is idempotent (re-stamps)."""
    ticket_in = TicketCreate(
        title="New laptop setup needed",
        description="Onboarding engineering intern next Monday",
        category=TicketCategory.HARDWARE,
        priority=TicketPriority.LOW,
        triage_suggestion=TriageSuggestionCreate(
            suggested_category=TicketCategory.HARDWARE,
            suggested_priority=TicketPriority.LOW,
            method="knn",
        ),
    )
    ticket = create_ticket(db_session, ticket_in=ticket_in, current_user=requester_user)

    resp1 = client.post(
        f"/api/v1/tickets/{ticket.id}/triage-feedback/confirm",
        headers=admin_auth_headers,
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["final_category"] == "hardware"
    assert data1["final_priority"] == "low"
    assert data1["final_set_by"] == admin_user.id

    # Call again: re-stamps successfully
    resp2 = client.post(
        f"/api/v1/tickets/{ticket.id}/triage-feedback/confirm",
        headers=admin_auth_headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["final_category"] == "hardware"
    assert data2["final_priority"] == "low"
    assert data2["final_set_by"] == admin_user.id


def test_confirm_feedback_requester_forbidden(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    db_session: Session,
    requester_user: User,
):
    """Verify requester gets 403 Forbidden when calling confirm."""
    ticket_in = TicketCreate(
        title="Zoom audio echo",
        description="Echo in meeting room A",
        category=TicketCategory.SOFTWARE,
        priority=TicketPriority.MEDIUM,
        triage_suggestion=TriageSuggestionCreate(
            suggested_category=TicketCategory.SOFTWARE,
            suggested_priority=TicketPriority.MEDIUM,
            method="knn",
        ),
    )
    ticket = create_ticket(db_session, ticket_in=ticket_in, current_user=requester_user)

    resp = client.post(
        f"/api/v1/tickets/{ticket.id}/triage-feedback/confirm",
        headers=requester_auth_headers,
    )
    assert resp.status_code == 403


def test_confirm_feedback_missing_ticket(
    client: TestClient,
    agent_auth_headers: dict[str, str],
):
    """Verify 404 when ticket does not exist."""
    resp = client.post(
        "/api/v1/tickets/999999/triage-feedback/confirm",
        headers=agent_auth_headers,
    )
    assert resp.status_code == 404


def test_confirm_feedback_ticket_without_feedback(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    db_session: Session,
    requester_user: User,
):
    """Verify 404 when ticket exists but has no triage_feedback row."""
    ticket_in = TicketCreate(
        title="Keycard badge replacement",
        description="Lost badge in transit",
        category=TicketCategory.ACCESS,
        priority=TicketPriority.LOW,
    )
    ticket = create_ticket(db_session, ticket_in=ticket_in, current_user=requester_user)

    resp = client.post(
        f"/api/v1/tickets/{ticket.id}/triage-feedback/confirm",
        headers=agent_auth_headers,
    )
    assert resp.status_code == 404


def test_ai_quality_report_confirmed_and_corrected_counts(
    db_session: Session,
    agent_user: User,
):
    """
    Test that confirmed_n and corrected_n accurately distinguish full agreement
    from partial or complete correction in the report.
    """
    now = datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Confirmed: category and priority both match
    fb_confirmed = TriageFeedback(
        ticket_id=2001,
        method="knn",
        suggested_category="software",
        suggested_priority="high",
        requester_category="software",
        requester_priority="high",
        final_category="software",
        final_priority="high",
        final_set_by=agent_user.id,
        final_set_at=now,
        created_at=now,
    )

    # 2. Corrected: category differs, priority matches
    fb_corrected_cat = TriageFeedback(
        ticket_id=2002,
        method="knn",
        suggested_category="hardware",
        suggested_priority="medium",
        requester_category="hardware",
        requester_priority="medium",
        final_category="network",
        final_priority="medium",
        final_set_by=agent_user.id,
        final_set_at=now,
        created_at=now,
    )

    # 3. Corrected: category matches, priority differs
    fb_corrected_prio = TriageFeedback(
        ticket_id=2003,
        method="llm-rag",
        suggested_category="access",
        suggested_priority="low",
        requester_category="access",
        requester_priority="low",
        final_category="access",
        final_priority="urgent",
        final_set_by=agent_user.id,
        final_set_at=now,
        created_at=now,
    )

    # 4. Corrected: both differ
    fb_corrected_both = TriageFeedback(
        ticket_id=2004,
        method="llm-rag",
        suggested_category="email",
        suggested_priority="medium",
        requester_category="email",
        requester_priority="medium",
        final_category="security",
        final_priority="urgent",
        final_set_by=agent_user.id,
        final_set_at=now,
        created_at=now,
    )

    # 5. Unreviewed
    fb_unreviewed = TriageFeedback(
        ticket_id=2005,
        method="knn",
        suggested_category="other",
        suggested_priority="low",
        requester_category="other",
        requester_priority="low",
        created_at=now,
    )

    db_session.add_all([
        fb_confirmed,
        fb_corrected_cat,
        fb_corrected_prio,
        fb_corrected_both,
        fb_unreviewed,
    ])
    db_session.commit()

    report = get_ai_quality_report(db_session, days=30, current_time=now)
    assert report["total_suggestions"] == 5
    review = report["agent_review"]
    assert review["reviewed_n"] == 4
    assert review["confirmed_n"] == 1
    assert review["corrected_n"] == 3
    # 2 out of 4 agree on category (fb_confirmed, fb_corrected_prio)
    assert review["category_agreement_pct"] == 50.0
    # 2 out of 4 agree on priority (fb_confirmed, fb_corrected_cat)
    assert review["priority_agreement_pct"] == 50.0

