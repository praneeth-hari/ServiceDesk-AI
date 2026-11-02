from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.models.enums import TicketCategory, TicketPriority, TicketStatus


class TicketsByStatusItem(BaseModel):
    """Report row: count of tickets grouped by status and priority."""
    status: TicketStatus
    priority: TicketPriority
    count: int

    model_config = ConfigDict(from_attributes=True)


class OverdueTicketItem(BaseModel):
    """Report row: overdue ticket details including requester and assignee."""
    id: int
    title: str
    status: TicketStatus
    priority: TicketPriority
    due_at: datetime
    requester_id: int
    requester_name: str
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ResolutionTimeItem(BaseModel):
    """Report row: average hours from creation to first resolution per assignee."""
    assignee_id: int
    assignee_name: str
    avg_resolution_hours: float
    ticket_count: int

    model_config = ConfigDict(from_attributes=True)


class AgentRankingItem(BaseModel):
    """Report row: agent ranked by number of tickets resolved."""
    rank: int
    agent_id: int
    agent_name: str
    resolved_count: int

    model_config = ConfigDict(from_attributes=True)


class DailyVolumeItem(BaseModel):
    """Report row: number of tickets created on a specific calendar day."""
    date: str
    ticket_count: int

    model_config = ConfigDict(from_attributes=True)


class SLABreachRateItem(BaseModel):
    """Report row: SLA breach rate and compliance per ticket priority."""
    priority: TicketPriority
    total_tickets: int
    met_sla: int
    breached_sla: int
    breach_rate: float

    model_config = ConfigDict(from_attributes=True)


class ResolutionTimeByCategoryItem(BaseModel):
    """Report row: average resolution time in hours grouped by category and priority."""
    category: TicketCategory
    priority: TicketPriority
    avg_resolution_hours: float
    ticket_count: int

    model_config = ConfigDict(from_attributes=True)


class AgentWorkloadItem(BaseModel):
    """Report row: open work, overdue count, and resolved tickets per agent."""
    agent_id: int
    agent_name: str
    open_tickets: int
    overdue_tickets: int
    resolved_tickets: int

    model_config = ConfigDict(from_attributes=True)


class TicketsByCategoryItem(BaseModel):
    """Report row: count of tickets grouped by category, optionally by status."""
    category: TicketCategory
    status: Optional[TicketStatus] = None
    count: int

    model_config = ConfigDict(from_attributes=True)

