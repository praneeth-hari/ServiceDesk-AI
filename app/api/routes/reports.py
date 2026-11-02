from typing import Sequence
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.enums import UserRole
from app.schemas.report import (
    AgentRankingItem,
    AgentWorkloadItem,
    DailyVolumeItem,
    OverdueTicketItem,
    ResolutionTimeByCategoryItem,
    ResolutionTimeItem,
    SLABreachRateItem,
    TicketsByCategoryItem,
    TicketsByStatusItem,
)
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

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_roles([UserRole.AGENT, UserRole.ADMIN]))],
)


@router.get(
    "/tickets-by-status",
    response_model=list[TicketsByStatusItem],
    status_code=status.HTTP_200_OK,
    summary="Count of tickets per status and priority",
)
def report_tickets_by_status(
    db: Session = Depends(get_db),
) -> Sequence[TicketsByStatusItem]:
    """Report counting tickets grouped by status and priority."""
    return get_tickets_by_status(db=db)


@router.get(
    "/overdue",
    response_model=list[OverdueTicketItem],
    status_code=status.HTTP_200_OK,
    summary="List overdue tickets with requester and assignee",
)
def report_overdue(
    db: Session = Depends(get_db),
) -> Sequence[OverdueTicketItem]:
    """Report overdue tickets (past due_at and status open or in_progress)."""
    return get_overdue_tickets(db=db)


@router.get(
    "/resolution-time",
    response_model=list[ResolutionTimeItem],
    status_code=status.HTTP_200_OK,
    summary="Average resolution time in hours per assignee",
)
def report_resolution_time(
    db: Session = Depends(get_db),
) -> Sequence[ResolutionTimeItem]:
    """Report average hours from creation to first resolution per assignee."""
    return get_resolution_time(db=db)


@router.get(
    "/agent-ranking",
    response_model=list[AgentRankingItem],
    status_code=status.HTTP_200_OK,
    summary="Agent ranking by number of tickets resolved",
)
def report_agent_ranking(
    db: Session = Depends(get_db),
) -> Sequence[AgentRankingItem]:
    """Report agents ranked by resolved tickets using RANK() window function."""
    return get_agent_ranking(db=db)


@router.get(
    "/daily-volume",
    response_model=list[DailyVolumeItem],
    status_code=status.HTTP_200_OK,
    summary="Tickets created per day",
)
def report_daily_volume(
    days: int = Query(default=30, ge=1, le=90, description="Window in days (1 to 90)"),
    db: Session = Depends(get_db),
) -> Sequence[DailyVolumeItem]:
    """Report ticket creation count per calendar day using a CTE."""
    return get_daily_volume(db=db, days=days)


@router.get(
    "/sla-breach-rate",
    response_model=list[SLABreachRateItem],
    status_code=status.HTTP_200_OK,
    summary="SLA breach rate per ticket priority",
)
def report_sla_breach_rate(
    db: Session = Depends(get_db),
) -> Sequence[SLABreachRateItem]:
    """Report SLA breach rate and compliance counts per priority."""
    return get_sla_breach_rate(db=db)


@router.get(
    "/resolution-time-by-category",
    response_model=list[ResolutionTimeByCategoryItem],
    status_code=status.HTTP_200_OK,
    summary="Average resolution time in hours per category and priority",
)
def report_resolution_time_by_category(
    db: Session = Depends(get_db),
) -> Sequence[ResolutionTimeByCategoryItem]:
    """Report average hours to first resolution grouped by category and priority."""
    return get_resolution_time_by_category(db=db)


@router.get(
    "/agent-workload",
    response_model=list[AgentWorkloadItem],
    status_code=status.HTTP_200_OK,
    summary="Agent workload summary",
)
def report_agent_workload(
    db: Session = Depends(get_db),
) -> Sequence[AgentWorkloadItem]:
    """Report open work, overdue tickets, and resolved tickets per agent."""
    return get_agent_workload(db=db)


@router.get(
    "/tickets-by-category",
    response_model=list[TicketsByCategoryItem],
    status_code=status.HTTP_200_OK,
    summary="Count of tickets per category",
)
def report_tickets_by_category(
    breakdown_by_status: bool = Query(
        default=False,
        description="Whether to break down category counts by status",
    ),
    db: Session = Depends(get_db),
) -> Sequence[TicketsByCategoryItem]:
    """Report count of tickets per category, optionally broken down by status."""
    return get_tickets_by_category(db=db, breakdown_by_status=breakdown_by_status)

