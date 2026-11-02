from typing import Literal, Optional, Sequence
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.ai.embedder import get_text_to_embed
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentRead
from app.schemas.history import StatusHistoryRead
from app.schemas.triage import SimilarTicket
from app.schemas.ticket import (
    PaginatedTickets,
    TicketAssign,
    TicketCreate,
    TicketRead,
    TicketStatusUpdate,
    TicketUpdate,
)
from app.services.comments import create_comment, list_comments
from app.services.tickets import (
    assign_ticket,
    create_ticket,
    get_ticket_by_id,
    get_ticket_status_history,
    list_tickets,
    update_ticket,
    update_ticket_status,
)
from app.services.triage import find_similar

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post(
    "",
    response_model=TicketRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ticket",
)
def create_new_ticket(
    ticket_in: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketRead:
    """
    Create a new support ticket. Requester is set to the authenticated user.
    """
    return create_ticket(db, ticket_in=ticket_in, current_user=current_user)


@router.get(
    "",
    response_model=PaginatedTickets,
    status_code=status.HTTP_200_OK,
    summary="List tickets",
)
def get_all_tickets(
    page: int = Query(default=1, ge=1, description="Page number, 1-indexed"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page, maximum 100"),
    status: Optional[TicketStatus] = Query(default=None, description="Filter by ticket status"),
    priority: Optional[TicketPriority] = Query(default=None, description="Filter by ticket priority"),
    category: Optional[TicketCategory] = Query(default=None, description="Filter by ticket category"),
    assignee_id: Optional[int] = Query(default=None, description="Filter by assigned agent ID"),
    overdue: Optional[bool] = Query(default=None, description="Filter by overdue status"),
    q: Optional[str] = Query(default=None, description="Keyword search across title and description"),
    sort_by: Literal["created_at", "updated_at", "due_at"] = Query(
        default="created_at", description="Field to sort by"
    ),
    order: Literal["asc", "desc"] = Query(
        default="desc", description="Sort direction ('asc' or 'desc')"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedTickets:
    """
    List tickets with pagination, filters, search, and sorting.
    Requesters see only their own tickets; agents and admins see all.
    """
    items, total = list_tickets(
        db=db,
        current_user=current_user,
        page=page,
        page_size=page_size,
        status=status,
        priority=priority,
        category=category,
        assignee_id=assignee_id,
        overdue=overdue,
        q=q,
        sort_by=sort_by,
        order=order,
    )
    return PaginatedTickets(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{id}",
    response_model=TicketRead,
    status_code=status.HTTP_200_OK,
    summary="Get ticket by ID",
)
def get_single_ticket(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketRead:
    """
    Get ticket details by ID. Requesters can only access their own tickets (404 otherwise).
    """
    return get_ticket_by_id(db, ticket_id=id, current_user=current_user)


@router.patch(
    "/{id}",
    response_model=TicketRead,
    status_code=status.HTTP_200_OK,
    summary="Update ticket content",
)
def update_ticket_content(
    id: int,
    ticket_in: TicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketRead:
    """
    Update ticket title, description, or priority. Allowed for owner while 'open', or admin.
    """
    return update_ticket(db, ticket_id=id, ticket_in=ticket_in, current_user=current_user)


@router.patch(
    "/{id}/status",
    response_model=TicketRead,
    status_code=status.HTTP_200_OK,
    summary="Update ticket status",
)
def change_ticket_status(
    id: int,
    status_in: TicketStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketRead:
    """
    Change ticket status according to the allowed workflow. Agents and admins only.
    """
    return update_ticket_status(db, ticket_id=id, status_in=status_in, current_user=current_user)


@router.patch(
    "/{id}/assign",
    response_model=TicketRead,
    status_code=status.HTTP_200_OK,
    summary="Assign ticket to an agent",
)
def assign_ticket_to_agent(
    id: int,
    assign_in: TicketAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketRead:
    """
    Assign a ticket to an active agent. If ticket was 'open', moves it to 'in_progress'. Agents and admins only.
    """
    return assign_ticket(db, ticket_id=id, assign_in=assign_in, current_user=current_user)


@router.post(
    "/{id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment to a ticket",
)
def add_comment_to_ticket(
    id: int,
    comment_in: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CommentRead:
    """
    Add a comment to a ticket. Owner, agents, and admins only. Only staff can mark is_internal=true.
    """
    return create_comment(db, ticket_id=id, comment_in=comment_in, current_user=current_user)


@router.get(
    "/{id}/comments",
    response_model=list[CommentRead],
    status_code=status.HTTP_200_OK,
    summary="List comments for a ticket",
)
def get_ticket_comments(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Sequence[CommentRead]:
    """
    List all comments on a ticket. Requesters cannot see internal comments.
    """
    return list_comments(db, ticket_id=id, current_user=current_user)


@router.get(
    "/{id}/history",
    response_model=list[StatusHistoryRead],
    status_code=status.HTTP_200_OK,
    summary="Get ticket status transition history",
)
def get_ticket_history(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Sequence[StatusHistoryRead]:
    """
    Get the audit trail of status changes for a ticket. Owner, agents, and admins only.
    """
    return get_ticket_status_history(db, ticket_id=id, current_user=current_user)


@router.get(
    "/{id}/similar",
    response_model=list[SimilarTicket],
    status_code=status.HTTP_200_OK,
    summary="Get similar tickets",
)
def get_similar_tickets(
    id: int,
    limit: int = Query(default=5, ge=1, le=20, description="Maximum number of similar tickets to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SimilarTicket]:
    """
    Get tickets similar to this ticket, excluding itself.
    Agent and admin only (403 for requesters, 404 if ticket does not exist).
    """
    if current_user.role not in (UserRole.AGENT, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only agents and admins can access similar tickets",
        )

    ticket = db.get(Ticket, id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    text = get_text_to_embed(ticket.title, ticket.description)
    results = find_similar(
        db=db,
        text=text,
        current_user=current_user,
        exclude_ticket_id=ticket.id,
        limit=limit,
    )
    return [SimilarTicket(**r) for r in results]
