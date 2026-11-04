import logging
from typing import Union
from fastapi import APIRouter, Depends, HTTPException, status
import sqlalchemy as sa
from sqlalchemy.orm import Session, joinedload

from app.ai.assist import build_assist_prompt, call_ollama_assist
from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.comment import TicketComment
from app.models.enums import UserRole
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.assist import (
    AIAssistRequest,
    AIAssistReplyResponse,
    AIAssistStatusResponse,
    AIAssistSummaryResponse,
)

logger = logging.getLogger("helpdesk_api")

router = APIRouter(tags=["ai-assist"])


@router.get(
    "/ai-assist/status",
    response_model=AIAssistStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get AI assist configuration status",
)
def get_ai_assist_status(
    current_user: User = Depends(get_current_user),
) -> AIAssistStatusResponse:
    """
    Get AI assist status (enabled, mode, model).
    Agent and admin only (403 for requesters).
    Does NOT contact Ollama.
    """
    if current_user.role not in (UserRole.AGENT, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only agents and admins can access AI assist status",
        )

    is_enabled = settings.AI_ASSIST_MODE == "ollama"
    model = settings.AI_ASSIST_MODEL if is_enabled else None
    return AIAssistStatusResponse(
        enabled=is_enabled,
        mode=settings.AI_ASSIST_MODE,
        model=model,
    )


@router.post(
    "/tickets/{ticket_id}/ai-assist",
    response_model=Union[AIAssistSummaryResponse, AIAssistReplyResponse],
    status_code=status.HTTP_200_OK,
    summary="Run AI assist (summary or draft reply) for a ticket",
)
def run_ai_assist(
    ticket_id: int,
    payload: AIAssistRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Union[AIAssistSummaryResponse, AIAssistReplyResponse]:
    """
    Generate an AI summary or draft reply for a ticket.
    Agent and admin only (403 for requesters, 404 if ticket missing).
    Returns 503 if AI assist is disabled.
    Returns 502 if Ollama fails or output is invalid.
    """
    if current_user.role not in (UserRole.AGENT, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only agents and admins can use AI assist",
        )

    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    if settings.AI_ASSIST_MODE == "off":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ai_assist_disabled",
                "message": "AI assist is disabled on this server.",
            },
        )

    # Load requester info for personalization
    requester = db.get(User, ticket.requester_id) if ticket.requester_id else None
    requester_name = requester.full_name if requester else "Requester"
    agent_name = current_user.full_name or "Support Agent"

    # Query public comments only, ordered oldest to newest
    stmt = (
        sa.select(TicketComment)
        .options(joinedload(TicketComment.author))
        .where(TicketComment.ticket_id == ticket.id)
        .where(TicketComment.is_internal == False)
        .order_by(TicketComment.created_at.asc(), TicketComment.id.asc())
    )
    public_comments = db.scalars(stmt).all()

    # Build prompt with injection protection and capping
    prompt = build_assist_prompt(
        ticket=ticket,
        requester_name=requester_name,
        agent_name=agent_name,
        public_comments=public_comments,
        task=payload.task,
    )

    # Call Ollama
    result_dict, latency_ms, error_reason = call_ollama_assist(
        user_prompt=prompt,
        task=payload.task,
        model_name=settings.AI_ASSIST_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        timeout=settings.AI_ASSIST_TIMEOUT_SECONDS,
    )

    if result_dict is None:
        logger.warning(
            "AI assist failed for ticket %d task=%s (reason: %s, latency: %dms)",
            ticket.id,
            payload.task,
            error_reason,
            latency_ms,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "ai_assist_unavailable",
                "message": "AI assist is currently unavailable.",
            },
        )

    logger.info(
        "AI assist succeeded for ticket %d task=%s in %dms",
        ticket.id,
        payload.task,
        latency_ms,
    )

    result_dict["model"] = settings.AI_ASSIST_MODEL
    result_dict["latency_ms"] = latency_ms

    if payload.task == "summary":
        return AIAssistSummaryResponse(**result_dict)
    return AIAssistReplyResponse(**result_dict)

