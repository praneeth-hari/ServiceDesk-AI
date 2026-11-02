from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence
import sqlalchemy as sa
from sqlalchemy.orm import Session


def get_hours_diff_expression(dialect_name: str, start_col: str, end_col: str) -> str:
    """
    Generate the SQL expression for calculating elapsed time in hours between two timestamp columns.
    
    Why this helper is needed:
    - MySQL has a dedicated TIMESTAMPDIFF(unit, start, end) function:
      TIMESTAMPDIFF(SECOND, start, end) / 3600.0 returns fractional hours.
    - SQLite does not have TIMESTAMPDIFF; instead it uses the julianday() function:
      (julianday(end) - julianday(start)) returns the difference in fractional days,
      which multiplied by 24.0 gives elapsed hours.
    """
    if dialect_name == "mysql":
        return f"(TIMESTAMPDIFF(SECOND, {start_col}, {end_col}) / 3600.0)"
    return f"((julianday({end_col}) - julianday({start_col})) * 24.0)"


def get_tickets_by_status(db: Session) -> Sequence[dict[str, Any]]:
    """
    Report 1: Count tickets per status and priority using GROUP BY.
    """
    stmt = sa.text("""
        SELECT 
            status, 
            priority, 
            COUNT(*) AS count
        FROM tickets
        GROUP BY status, priority
        ORDER BY status, priority
    """)
    result = db.execute(stmt)
    return result.mappings().all()


def get_overdue_tickets(
    db: Session,
    current_time: Optional[datetime] = None,
) -> Sequence[dict[str, Any]]:
    """
    Report 2: Overdue tickets (due_at in the past, status open or in_progress)
    with the requester's name and assignee's name (or null).
    Uses INNER JOIN for requester and LEFT JOIN for assignee.
    """
    now = current_time or datetime.now(timezone.utc)
    stmt = sa.text("""
        SELECT 
            t.id,
            t.title,
            t.status,
            t.priority,
            t.due_at,
            t.requester_id,
            r.full_name AS requester_name,
            t.assignee_id,
            a.full_name AS assignee_name
        FROM tickets t
        JOIN users r ON t.requester_id = r.id
        LEFT JOIN users a ON t.assignee_id = a.id
        WHERE t.due_at < :now
          AND t.status IN ('open', 'in_progress')
          AND t.sla_paused_at IS NULL
        ORDER BY t.due_at ASC, t.id ASC
    """)
    result = db.execute(stmt, {"now": now})
    return result.mappings().all()


def get_resolution_time(db: Session) -> Sequence[dict[str, Any]]:
    """
    Report 3: Average hours from ticket creation to the first 'resolved' entry
    in ticket_status_history, per assignee, using a CTE.
    Only counts tickets that have a resolved entry.
    """
    dialect_name = db.get_bind().dialect.name
    diff_expr = get_hours_diff_expression(dialect_name, "t.created_at", "fr.resolved_at")

    stmt = sa.text(f"""
        WITH first_resolved AS (
            SELECT 
                ticket_id, 
                MIN(created_at) AS resolved_at
            FROM ticket_status_history
            WHERE to_status = 'resolved'
            GROUP BY ticket_id
        ),
        ticket_resolution AS (
            SELECT 
                t.id AS ticket_id,
                t.assignee_id,
                u.full_name AS assignee_name,
                {diff_expr} AS resolution_hours
            FROM tickets t
            JOIN first_resolved fr ON t.id = fr.ticket_id
            JOIN users u ON t.assignee_id = u.id
        )
        SELECT 
            assignee_id,
            assignee_name,
            ROUND(AVG(resolution_hours), 2) AS avg_resolution_hours,
            COUNT(*) AS ticket_count
        FROM ticket_resolution
        GROUP BY assignee_id, assignee_name
        ORDER BY avg_resolution_hours ASC, assignee_id ASC
    """)
    result = db.execute(stmt)
    return result.mappings().all()


def get_agent_ranking(db: Session) -> Sequence[dict[str, Any]]:
    """
    Report 4: Agents ranked by number of tickets resolved using RANK() OVER (ORDER BY ... DESC).
    Ties share a rank.
    """
    stmt = sa.text("""
        WITH agent_counts AS (
            SELECT 
                u.id AS agent_id,
                u.full_name AS agent_name,
                COUNT(t.id) AS resolved_count
            FROM users u
            JOIN tickets t ON t.assignee_id = u.id AND t.status IN ('resolved', 'closed')
            WHERE u.role = 'agent'
            GROUP BY u.id, u.full_name
        )
        SELECT 
            agent_id,
            agent_name,
            resolved_count,
            RANK() OVER (ORDER BY resolved_count DESC) AS `rank`
        FROM agent_counts
        ORDER BY `rank` ASC, agent_id ASC
    """)
    result = db.execute(stmt)
    return result.mappings().all()


def get_daily_volume(
    db: Session,
    days: int = 30,
    current_time: Optional[datetime] = None,
) -> Sequence[dict[str, Any]]:
    """
    Report 5: Tickets created per day over the last N days using a CTE.
    Days with zero tickets may be left out.
    """
    now = current_time or datetime.now(timezone.utc)
    since_date = now - timedelta(days=days)

    stmt = sa.text("""
        WITH daily_tickets AS (
            SELECT 
                DATE(created_at) AS ticket_date,
                id
            FROM tickets
            WHERE created_at >= :since_date
        )
        SELECT 
            ticket_date AS `date`,
            COUNT(id) AS ticket_count
        FROM daily_tickets
        GROUP BY ticket_date
        ORDER BY ticket_date ASC
    """)
    result = db.execute(stmt, {"since_date": since_date})
    return result.mappings().all()


def get_sla_breach_rate(
    db: Session,
    current_time: Optional[datetime] = None,
) -> Sequence[dict[str, Any]]:
    """
    Report 6: SLA breach rate per priority.
    - Total tickets, tickets that met SLA, tickets that breached SLA.
    - Breach: resolved or closed after due_at, OR still unresolved and past due_at.
    - Uses status history to find when a ticket was first resolved.
    - breach_rate as percentage rounded to 1 decimal.
    - Avoids division by zero.
    - Stable ordering by priority ASC.
    """
    now = current_time or datetime.now(timezone.utc)
    stmt = sa.text("""
        WITH first_resolved AS (
            SELECT 
                ticket_id, 
                MIN(created_at) AS resolved_at
            FROM ticket_status_history
            WHERE to_status = 'resolved'
            GROUP BY ticket_id
        ),
        ticket_breach AS (
            SELECT 
                t.id,
                t.priority,
                CASE 
                    WHEN t.due_at IS NOT NULL AND fr.resolved_at IS NOT NULL AND fr.resolved_at > t.due_at THEN 1
                    WHEN t.due_at IS NOT NULL AND fr.resolved_at IS NULL AND t.status IN ('resolved', 'closed') AND t.updated_at > t.due_at THEN 1
                    WHEN t.due_at IS NOT NULL AND t.status IN ('open', 'in_progress', 'waiting_on_requester') AND t.sla_paused_at IS NULL AND t.due_at < :now THEN 1
                    ELSE 0
                END AS is_breached
            FROM tickets t
            LEFT JOIN first_resolved fr ON t.id = fr.ticket_id
        )
        SELECT 
            priority,
            COUNT(*) AS total_tickets,
            SUM(CASE WHEN is_breached = 0 THEN 1 ELSE 0 END) AS met_sla,
            SUM(CASE WHEN is_breached = 1 THEN 1 ELSE 0 END) AS breached_sla,
            CASE 
                WHEN COUNT(*) > 0 THEN ROUND(100.0 * SUM(CASE WHEN is_breached = 1 THEN 1.0 ELSE 0.0 END) / COUNT(*), 1)
                ELSE 0.0 
            END AS breach_rate
        FROM ticket_breach
        GROUP BY priority
        ORDER BY priority ASC
    """)
    result = db.execute(stmt, {"now": now})
    return result.mappings().all()


def get_resolution_time_by_category(db: Session) -> Sequence[dict[str, Any]]:
    """
    Report 7: Average resolution time in hours per category and priority.
    - Only for tickets that have been resolved (using first resolved entry in status history).
    - Resolution hours = first resolved time minus created_at.
    - Uses get_hours_diff_expression for MySQL and SQLite compatibility.
    - Stable ordering by category ASC, priority ASC.
    """
    dialect_name = db.get_bind().dialect.name
    diff_expr = get_hours_diff_expression(dialect_name, "t.created_at", "fr.resolved_at")

    stmt = sa.text(f"""
        WITH first_resolved AS (
            SELECT 
                ticket_id, 
                MIN(created_at) AS resolved_at
            FROM ticket_status_history
            WHERE to_status = 'resolved'
            GROUP BY ticket_id
        ),
        ticket_resolution AS (
            SELECT 
                t.id AS ticket_id,
                t.category,
                t.priority,
                {diff_expr} AS resolution_hours
            FROM tickets t
            JOIN first_resolved fr ON t.id = fr.ticket_id
        )
        SELECT 
            category,
            priority,
            ROUND(AVG(resolution_hours), 2) AS avg_resolution_hours,
            COUNT(*) AS ticket_count
        FROM ticket_resolution
        GROUP BY category, priority
        ORDER BY category ASC, priority ASC
    """)
    result = db.execute(stmt)
    return result.mappings().all()


def get_agent_workload(
    db: Session,
    current_time: Optional[datetime] = None,
) -> Sequence[dict[str, Any]]:
    """
    Report 8: Agent workload summary.
    - Open work (open + in_progress) assigned to the agent.
    - Overdue count among open work assigned to the agent (past due_at).
    - Resolved tickets assigned to the agent (status resolved or closed).
    - Includes agents with zero tickets via LEFT JOIN.
    - Uses CTE.
    - Stable ordering by open_tickets DESC, agent_id ASC.
    """
    now = current_time or datetime.now(timezone.utc)
    stmt = sa.text("""
        WITH agent_tickets AS (
            SELECT 
                u.id AS agent_id,
                u.full_name AS agent_name,
                t.id AS ticket_id,
                t.status,
                t.due_at,
                t.sla_paused_at
            FROM users u
            LEFT JOIN tickets t ON t.assignee_id = u.id
            WHERE u.role = 'agent'
        )
        SELECT 
            agent_id,
            agent_name,
            COUNT(CASE WHEN status IN ('open', 'in_progress', 'waiting_on_requester') THEN 1 END) AS open_tickets,
            COUNT(CASE WHEN status IN ('open', 'in_progress', 'waiting_on_requester') AND sla_paused_at IS NULL AND due_at IS NOT NULL AND due_at < :now THEN 1 END) AS overdue_tickets,
            COUNT(CASE WHEN status IN ('resolved', 'closed') THEN 1 END) AS resolved_tickets
        FROM agent_tickets
        GROUP BY agent_id, agent_name
        ORDER BY open_tickets DESC, agent_id ASC
    """)
    result = db.execute(stmt, {"now": now})
    return result.mappings().all()


def get_tickets_by_category(
    db: Session,
    breakdown_by_status: bool = False,
) -> Sequence[dict[str, Any]]:
    """
    Report 9: Ticket count per category, optionally broken down by status.
    - If breakdown_by_status is False: groups by category only, status is None, ordered by count DESC, category ASC.
    - If breakdown_by_status is True: groups by category and status, ordered by category ASC, status ASC.
    """
    if breakdown_by_status:
        stmt = sa.text("""
            SELECT 
                category,
                status,
                COUNT(*) AS count
            FROM tickets
            GROUP BY category, status
            ORDER BY category ASC, status ASC
        """)
    else:
        stmt = sa.text("""
            SELECT 
                category,
                NULL AS status,
                COUNT(*) AS count
            FROM tickets
            GROUP BY category
            ORDER BY count DESC, category ASC
        """)
    result = db.execute(stmt)
    return result.mappings().all()

