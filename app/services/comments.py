from datetime import datetime, timezone
from typing import Sequence
from fastapi import HTTPException, status
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.comment import TicketComment
from app.models.enums import TicketStatus, UserRole
from app.models.user import User
from app.schemas.comment import CommentCreate
from app.services.tickets import get_ticket_by_id


def create_comment(
    db: Session,
    ticket_id: int,
    comment_in: CommentCreate,
    current_user: User,
) -> TicketComment:
    """
    Add a comment to a ticket:
    - Ticket owner, agents, and admins can add comments.
    - Other requesters receive 404 (handled by get_ticket_by_id).
    - Closed tickets cannot receive new comments (409 Conflict).
    - Only agents and admins can set is_internal=True (403 Forbidden for requesters).
    """
    ticket = get_ticket_by_id(db, ticket_id=ticket_id, current_user=current_user)

    is_owner = ticket.requester_id == current_user.id
    is_staff = current_user.role in (UserRole.AGENT, UserRole.ADMIN)

    if not (is_owner or is_staff):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to comment on this ticket",
        )

    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot add comments to a closed ticket",
        )

    if comment_in.is_internal and not is_staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requesters cannot create internal comments",
        )

    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=current_user.id,
        body=comment_in.body,
        is_internal=comment_in.is_internal,
        created_at=datetime.now(timezone.utc),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def list_comments(
    db: Session,
    ticket_id: int,
    current_user: User,
) -> Sequence[TicketComment]:
    """
    List comments for a ticket:
    - Anyone who can view the ticket can read its comments.
    - Requesters never receive internal comments (filtered out cleanly).
    - Agents and admins see all comments, including internal notes.
    """
    ticket = get_ticket_by_id(db, ticket_id=ticket_id, current_user=current_user)

    stmt = sa.select(TicketComment).where(TicketComment.ticket_id == ticket.id)

    if current_user.role == UserRole.REQUESTER:
        stmt = stmt.where(TicketComment.is_internal == False)

    stmt = stmt.order_by(TicketComment.created_at.asc(), TicketComment.id.asc())
    return db.scalars(stmt).all()
