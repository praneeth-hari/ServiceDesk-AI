from datetime import datetime, timezone
from typing import Optional, Sequence
from fastapi import HTTPException, status
import sqlalchemy as sa
from sqlalchemy.orm import Session, joinedload

from app.core.sla import add_business_minutes, business_minutes_between, calculate_due_at
from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.history import TicketStatusHistory
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket import (
    TicketAssign,
    TicketCreate,
    TicketStatusUpdate,
    TicketUpdate,
)
from app.services.holidays import get_holiday_dates
from app.services.triage import sync_ticket_embedding

# Allowed status workflow transitions
ALLOWED_STATUS_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.OPEN: {TicketStatus.IN_PROGRESS},
    TicketStatus.IN_PROGRESS: {TicketStatus.RESOLVED, TicketStatus.WAITING_ON_REQUESTER},
    TicketStatus.WAITING_ON_REQUESTER: {TicketStatus.IN_PROGRESS},
    TicketStatus.RESOLVED: {TicketStatus.CLOSED, TicketStatus.IN_PROGRESS},
    TicketStatus.CLOSED: set(),
}


def create_ticket(
    db: Session,
    ticket_in: TicketCreate,
    current_user: User,
    current_time: Optional[datetime] = None,
) -> Ticket:
    """
    Create a new ticket.
    - requester_id is set exclusively from current_user.
    - Status always starts as 'open'.
    - due_at is calculated as created_at + SLA hours for the chosen priority.
    - category defaults to 'other' or the value provided.
    - Records initial status history (from_status=None -> to_status='open').
    """
    now = current_time or datetime.now(timezone.utc)
    holidays = get_holiday_dates(db)
    due_at = calculate_due_at(ticket_in.priority, now, holidays=holidays)

    ticket = Ticket(
        title=ticket_in.title,
        description=ticket_in.description,
        priority=ticket_in.priority,
        category=ticket_in.category,
        status=TicketStatus.OPEN,
        requester_id=current_user.id,
        assignee_id=None,
        due_at=due_at,
        sla_paused_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.flush()

    # Record initial status history
    history_entry = TicketStatusHistory(
        ticket_id=ticket.id,
        changed_by_id=current_user.id,
        from_status=None,
        to_status=TicketStatus.OPEN,
        created_at=now,
    )
    db.add(history_entry)

    # Sync embedding (failure is logged and ignored to never break ticket creation)
    sync_ticket_embedding(db, ticket)

    db.commit()
    return get_ticket_by_id(db, ticket_id=ticket.id, current_user=current_user)


def get_ticket_by_id(db: Session, ticket_id: int, current_user: User) -> Ticket:
    """
    Retrieve a ticket by ID.
    - If ticket doesn't exist: returns 404.
    - If user is a requester and not the owner: returns 404 (not 403).
    - Agents and admins can view any ticket.
    - Eagerly loads requester and assignee to populate names.
    """
    stmt = (
        sa.select(Ticket)
        .options(
            joinedload(Ticket.requester),
            joinedload(Ticket.assignee),
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = db.scalars(stmt).unique().first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    if current_user.role == UserRole.REQUESTER and ticket.requester_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    return ticket


def escape_like_term(term: str) -> str:
    """Escape SQL LIKE wildcards '%' and '_' as well as the escape character itself."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_tickets(
    db: Session,
    current_user: User,
    page: int = 1,
    page_size: int = 20,
    status: Optional[TicketStatus] = None,
    priority: Optional[TicketPriority] = None,
    category: Optional[TicketCategory] = None,
    assignee_id: Optional[int] = None,
    overdue: Optional[bool] = None,
    q: Optional[str] = None,
    sort_by: str = "created_at",
    order: str = "desc",
    current_time: Optional[datetime] = None,
) -> tuple[Sequence[Ticket], int]:
    """
    List tickets with pagination, filters, search, and sorting:
    - Requesters see only their own tickets.
    - Agents and admins see all tickets.
    - Filters: status, priority, category, assignee_id, overdue (same rule as is_overdue).
    - Keyword search 'q' across title and description with escaped wildcards.
    - Sorting by created_at, updated_at, or due_at with id as secondary tie-breaker.
    - total is computed from a separate count query on the filtered dataset.
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="page must be greater than or equal to 1",
        )
    if page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="page_size must be between 1 and 100",
        )

    allowed_sort_fields = {
        "created_at": Ticket.created_at,
        "updated_at": Ticket.updated_at,
        "due_at": Ticket.due_at,
    }
    if sort_by not in allowed_sort_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid sort_by field: '{sort_by}'. Allowed: {', '.join(allowed_sort_fields.keys())}",
        )
    if order not in ("asc", "desc"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid order: '{order}'. Allowed: 'asc', 'desc'",
        )

    stmt = sa.select(Ticket)

    # 1. Visibility rule first: requesters only see their own tickets
    if current_user.role == UserRole.REQUESTER:
        stmt = stmt.where(Ticket.requester_id == current_user.id)

    # 2. Filters
    if status is not None:
        stmt = stmt.where(Ticket.status == status)

    if priority is not None:
        stmt = stmt.where(Ticket.priority == priority)

    if category is not None:
        stmt = stmt.where(Ticket.category == category)

    if assignee_id is not None:
        stmt = stmt.where(Ticket.assignee_id == assignee_id)

    if overdue is not None:
        now = current_time or datetime.now(timezone.utc)
        if overdue is True:
            stmt = stmt.where(
                Ticket.due_at.is_not(None),
                Ticket.due_at < now,
                Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]),
                Ticket.sla_paused_at.is_(None),
            )
        else:
            stmt = stmt.where(
                sa.or_(
                    Ticket.due_at.is_(None),
                    Ticket.due_at >= now,
                    Ticket.status.notin_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]),
                    Ticket.sla_paused_at.is_not(None),
                )
            )

    # 3. Keyword search (case-insensitive across title and description)
    if q is not None and q.strip():
        escaped_q = escape_like_term(q.strip())
        pattern = f"%{escaped_q}%"
        stmt = stmt.where(
            sa.or_(
                Ticket.title.ilike(pattern, escape="\\"),
                Ticket.description.ilike(pattern, escape="\\"),
            )
        )

    # 4. Total count query on the filtered query (before ordering and pagination)
    count_stmt = sa.select(sa.func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    # 5. Sorting (primary column + id as secondary tie-breaker)
    col = allowed_sort_fields[sort_by]
    if order == "asc":
        stmt = stmt.order_by(col.asc(), Ticket.id.asc())
    else:
        stmt = stmt.order_by(col.desc(), Ticket.id.desc())

    # 6. Pagination & eager loading of related users to avoid N+1 queries
    offset = (page - 1) * page_size
    stmt = (
        stmt.offset(offset)
        .limit(page_size)
        .options(
            joinedload(Ticket.requester),
            joinedload(Ticket.assignee),
        )
    )

    items = db.scalars(stmt).unique().all()
    return items, total


def update_ticket(
    db: Session,
    ticket_id: int,
    ticket_in: TicketUpdate,
    current_user: User,
    current_time: Optional[datetime] = None,
) -> Ticket:
    """
    Update ticket title, description, priority, or category:
    - Allowed for the ticket owner while the ticket is 'open' (title, description, priority, category).
    - Allowed for admins anytime (all fields).
    - Allowed for agents anytime (category only).
    - Recalculates due_at from created_at if priority changes while open or in_progress.
    - Does not change due_at once the ticket is resolved or closed.
    """
    ticket = get_ticket_by_id(db, ticket_id=ticket_id, current_user=current_user)

    is_owner = ticket.requester_id == current_user.id
    is_admin = current_user.role == UserRole.ADMIN
    is_agent = current_user.role == UserRole.AGENT

    if not is_admin:
        if is_agent:
            if (
                ticket_in.title is not None
                or ticket_in.description is not None
                or ticket_in.priority is not None
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Agents can only update ticket category",
                )
        elif is_owner:
            if ticket.status != TicketStatus.OPEN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Requesters can only edit tickets while they are open",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to edit this ticket",
            )

    has_changed = False
    text_changed = False
    if ticket_in.title is not None and ticket_in.title != ticket.title:
        ticket.title = ticket_in.title
        has_changed = True
        text_changed = True
    if ticket_in.description is not None and ticket_in.description != ticket.description:
        ticket.description = ticket_in.description
        has_changed = True
        text_changed = True
    if ticket_in.priority is not None and ticket_in.priority != ticket.priority:
        ticket.priority = ticket_in.priority
        has_changed = True

        # Recalculate due_at from created_at only if open or in_progress
        if ticket.status in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS):
            created = ticket.created_at if ticket.created_at.tzinfo else ticket.created_at.replace(tzinfo=timezone.utc)
            holidays = get_holiday_dates(db)
            ticket.due_at = calculate_due_at(ticket.priority, created, holidays=holidays)

    if ticket_in.category is not None and ticket_in.category != ticket.category:
        ticket.category = ticket_in.category
        has_changed = True

    if has_changed:
        if text_changed:
            sync_ticket_embedding(db, ticket)

        ticket.updated_at = current_time or datetime.now(timezone.utc)
        db.commit()
        return get_ticket_by_id(db, ticket_id=ticket.id, current_user=current_user)

    return ticket


def update_ticket_status(
    db: Session,
    ticket_id: int,
    status_in: TicketStatusUpdate,
    current_user: User,
    current_time: Optional[datetime] = None,
) -> Ticket:
    """
    Update ticket status:
    - Allowed for agents and admins only (403 for requesters).
    - Transitions must follow the workflow (409 on invalid transition).
    - Writes an entry to status history and updates status in a single commit.
    """
    if current_user.role not in (UserRole.AGENT, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only agents and admins can update ticket status",
        )

    ticket = get_ticket_by_id(db, ticket_id=ticket_id, current_user=current_user)
    allowed_next_statuses = ALLOWED_STATUS_TRANSITIONS.get(ticket.status, set())

    if status_in.status not in allowed_next_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot transition ticket status from '{ticket.status.value}' "
                f"to '{status_in.status.value}'"
            ),
        )

    now = current_time or datetime.now(timezone.utc)
    old_status = ticket.status

    # Pausable SLA Clock
    if status_in.status == TicketStatus.WAITING_ON_REQUESTER:
        ticket.sla_paused_at = now
    elif old_status == TicketStatus.WAITING_ON_REQUESTER and status_in.status == TicketStatus.IN_PROGRESS:
        holidays = get_holiday_dates(db)
        paused_start = ticket.sla_paused_at or now
        paused_minutes = business_minutes_between(paused_start, now, holidays)
        if ticket.due_at is not None and paused_minutes > 0:
            ticket.due_at = add_business_minutes(ticket.due_at, paused_minutes, holidays)
        ticket.sla_paused_at = None

    ticket.status = status_in.status
    ticket.updated_at = now

    history_entry = TicketStatusHistory(
        ticket_id=ticket.id,
        changed_by_id=current_user.id,
        from_status=old_status,
        to_status=status_in.status,
        created_at=now,
    )
    db.add(history_entry)

    db.commit()
    return get_ticket_by_id(db, ticket_id=ticket.id, current_user=current_user)


def assign_ticket(
    db: Session,
    ticket_id: int,
    assign_in: TicketAssign,
    current_user: User,
    current_time: Optional[datetime] = None,
) -> Ticket:
    """
    Assign ticket to an agent:
    - Allowed for agents and admins only (403 for requesters).
    - Cannot assign a closed ticket (409 Conflict).
    - Assignee must exist (404).
    - Assignee must have 'agent' role and be active (422).
    - If the ticket is currently 'open', moving it to an agent changes status to 'in_progress'
      and writes an entry to status history.
    """
    if current_user.role not in (UserRole.AGENT, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only agents and admins can assign tickets",
        )

    ticket = get_ticket_by_id(db, ticket_id=ticket_id, current_user=current_user)

    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot assign a closed ticket",
        )

    assignee = db.get(User, assign_in.assignee_id)
    if not assignee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignee user not found",
        )

    if assignee.role != UserRole.AGENT or not assignee.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Assignee must be an active agent",
        )

    now = current_time or datetime.now(timezone.utc)
    ticket.assignee_id = assignee.id

    # Assigning an open ticket moves it to in_progress and records status history
    if ticket.status == TicketStatus.OPEN:
        old_status = ticket.status
        ticket.status = TicketStatus.IN_PROGRESS
        history_entry = TicketStatusHistory(
            ticket_id=ticket.id,
            changed_by_id=current_user.id,
            from_status=old_status,
            to_status=TicketStatus.IN_PROGRESS,
            created_at=now,
        )
        db.add(history_entry)

    ticket.updated_at = now
    db.commit()
    return get_ticket_by_id(db, ticket_id=ticket.id, current_user=current_user)


def get_ticket_status_history(
    db: Session,
    ticket_id: int,
    current_user: User,
) -> Sequence[TicketStatusHistory]:
    """
    Retrieve the status transition history for a ticket.
    - Owner, agents, and admins can view history.
    - Another requester gets 404 (handled by get_ticket_by_id).
    - Ordered by created_at then id ascending.
    """
    ticket = get_ticket_by_id(db, ticket_id=ticket_id, current_user=current_user)

    stmt = (
        sa.select(TicketStatusHistory)
        .where(TicketStatusHistory.ticket_id == ticket.id)
        .order_by(TicketStatusHistory.created_at.asc(), TicketStatusHistory.id.asc())
    )
    return db.scalars(stmt).all()
