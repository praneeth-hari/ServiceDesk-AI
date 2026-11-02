import argparse
from datetime import datetime, timedelta, timezone
import os
import sys
from typing import Any, Optional
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.comment import CommentCreate
from app.schemas.ticket import TicketAssign, TicketCreate, TicketStatusUpdate
from app.services.comments import create_comment
from app.services.tickets import assign_ticket, create_ticket, update_ticket_status
from app.services.users import get_user_by_email

DEMO_USERS = [
    {
        "email": "admin@example.com",
        "full_name": "System Admin",
        "password": "AdminPassword123!",
        "role": UserRole.ADMIN,
    },
    {
        "email": "agent@example.com",
        "full_name": "Asha Agent",
        "password": "AgentPassword123!",
        "role": UserRole.AGENT,
    },
    {
        "email": "requester@example.com",
        "full_name": "Ravi Requester",
        "password": "RequesterPassword123!",
        "role": UserRole.REQUESTER,
    },
]

DEMO_TICKETS = [
    {
        "title": "VPN disconnects often",
        "description": "GlobalProtect VPN client disconnects unexpectedly every 15 to 20 minutes when working remotely.",
        "category": TicketCategory.NETWORK,
        "priority": TicketPriority.HIGH,
        "owner_email": "requester@example.com",
        "assign_to_agent": True,
        "final_status": TicketStatus.IN_PROGRESS,
        "is_overdue": True,
        "overdue_delta": timedelta(hours=12),
        "comments": [
            {
                "author_email": "agent@example.com",
                "body": "Could you check if you have stable Wi-Fi or if packet loss occurs on ping 8.8.8.8?",
                "is_internal": False,
            },
            {
                "author_email": "requester@example.com",
                "body": "Ping shows 0% loss on local network. Seems like VPN gateway re-authentication timeout.",
                "is_internal": False,
            },
            {
                "author_email": "agent@example.com",
                "body": "Checked gateway logs; seeing multiple tunnel keepalive timeouts. Escalated to network engineering.",
                "is_internal": True,
            },
        ],
    },
    {
        "title": "Email not syncing on mobile",
        "description": "Outlook mobile app on iOS is not receiving new emails since password update yesterday.",
        "category": TicketCategory.EMAIL,
        "priority": TicketPriority.MEDIUM,
        "owner_email": "requester@example.com",
        "assign_to_agent": True,
        "final_status": TicketStatus.WAITING_ON_REQUESTER,
        "is_overdue": False,
        "comments": [
            {
                "author_email": "agent@example.com",
                "body": "Please remove the account from Outlook mobile settings and re-add via Modern Auth SSO.",
                "is_internal": False,
            },
        ],
    },
    {
        "title": "Printer not working on 3rd floor",
        "description": "HP LaserJet on 3rd floor East wing shows error 50.4 Fuser Error and will not print.",
        "category": TicketCategory.HARDWARE,
        "priority": TicketPriority.LOW,
        "owner_email": "requester@example.com",
        "assign_to_agent": True,
        "final_status": TicketStatus.RESOLVED,
        "is_overdue": False,
        "comments": [
            {
                "author_email": "agent@example.com",
                "body": "Fuser unit replaced and test print completed.",
                "is_internal": False,
            },
        ],
    },
    {
        "title": "Request new laptop for new hire",
        "description": "Standard developer MacBook Pro 16-inch requested for engineering hire joining next Monday.",
        "category": TicketCategory.HARDWARE,
        "priority": TicketPriority.MEDIUM,
        "owner_email": "requester@example.com",
        "assign_to_agent": True,
        "final_status": TicketStatus.RESOLVED,
        "is_overdue": False,
        "comments": [
            {
                "author_email": "agent@example.com",
                "body": "MacBook configured with base IT image and ready for pickup at IT helpdesk.",
                "is_internal": False,
            },
        ],
    },
    {
        "title": "Password reset needed for HR portal",
        "description": "Locked out of Workday HR portal after entering temporary password multiple times.",
        "category": TicketCategory.ACCESS,
        "priority": TicketPriority.URGENT,
        "owner_email": "requester@example.com",
        "assign_to_agent": True,
        "final_status": TicketStatus.IN_PROGRESS,
        "is_overdue": True,
        "overdue_delta": timedelta(hours=4),
        "comments": [],
    },
    {
        "title": "WiFi slow in lab area",
        "description": "Download speed in hardware testing lab is below 2 Mbps with severe latency spikes.",
        "category": TicketCategory.NETWORK,
        "priority": TicketPriority.MEDIUM,
        "owner_email": "requester@example.com",
        "assign_to_agent": False,
        "final_status": TicketStatus.OPEN,
        "is_overdue": True,
        "overdue_delta": timedelta(days=2),
        "comments": [],
    },
    {
        "title": "Database client software crashes on startup",
        "description": "DBeaver 24.1 crashes with JVM exit code 1 immediately upon launch on Windows 11.",
        "category": TicketCategory.SOFTWARE,
        "priority": TicketPriority.HIGH,
        "owner_email": "requester@example.com",
        "assign_to_agent": True,
        "final_status": TicketStatus.IN_PROGRESS,
        "is_overdue": False,
        "comments": [
            {
                "author_email": "agent@example.com",
                "body": "JDK 21 path conflict in user PATH variable. Scheduled remote assist session.",
                "is_internal": True,
            },
        ],
    },
    {
        "title": "Request access to GitHub organization",
        "description": "Need read/write access to internal backend repositories for the HelpDesk project.",
        "category": TicketCategory.ACCESS,
        "priority": TicketPriority.LOW,
        "owner_email": "requester@example.com",
        "assign_to_agent": False,
        "final_status": TicketStatus.OPEN,
        "is_overdue": False,
        "comments": [],
    },
    {
        "title": "Security badge reader issue at main entrance",
        "description": "Turnstile badge reader 3 intermittently fails to read NFC cards during morning rush.",
        "category": TicketCategory.OTHER,
        "priority": TicketPriority.URGENT,
        "owner_email": "admin@example.com",
        "assign_to_agent": True,
        "final_status": TicketStatus.CLOSED,
        "is_overdue": False,
        "comments": [
            {
                "author_email": "agent@example.com",
                "body": "Facilities team replaced the RFID antenna module and validated 50 badge swipes.",
                "is_internal": True,
            },
            {
                "author_email": "agent@example.com",
                "body": "Turnstile 3 RFID antenna has been replaced and verified functional.",
                "is_internal": False,
            },
        ],
    },
    {
        "title": "License renewal for design tool",
        "description": "Annual Figma enterprise license seat expiring at the end of the month.",
        "category": TicketCategory.SOFTWARE,
        "priority": TicketPriority.LOW,
        "owner_email": "requester@example.com",
        "assign_to_agent": False,
        "final_status": TicketStatus.OPEN,
        "is_overdue": False,
        "comments": [],
    },
]


def _seed_demo_data(session: Session) -> dict[str, int]:
    """Execute demo data seeding within the given database session."""
    users_by_email: dict[str, User] = {}
    users_created = 0
    users_existing = 0

    # 1. Create or verify demo users
    for spec in DEMO_USERS:
        email = spec["email"]
        user = get_user_by_email(session, email=email)
        if user:
            users_existing += 1
            if user.role != spec["role"]:
                user.role = spec["role"]
                session.commit()
                session.refresh(user)
        else:
            user = User(
                email=email,
                full_name=spec["full_name"],
                hashed_password=hash_password(spec["password"]),
                role=spec["role"],
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            users_created += 1
        users_by_email[email] = user

    admin_user = users_by_email["admin@example.com"]
    agent_user = users_by_email["agent@example.com"]

    tickets_created = 0
    tickets_skipped = 0
    comments_created = 0
    overdue_count = 0

    now = datetime.now(timezone.utc)

    # 2. Create sample tickets idempotently
    for t_spec in DEMO_TICKETS:
        owner = users_by_email[t_spec["owner_email"]]

        # Check if already exists (by title and requester_id)
        existing_ticket = session.scalars(
            sa.select(Ticket).where(
                Ticket.title == t_spec["title"],
                Ticket.requester_id == owner.id,
            )
        ).first()

        if existing_ticket:
            tickets_skipped += 1
            continue

        # Create ticket via service function so SLA, created_at, status history are authentic
        ticket_in = TicketCreate(
            title=t_spec["title"],
            description=t_spec["description"],
            priority=t_spec["priority"],
            category=t_spec["category"],
        )
        ticket = create_ticket(session, ticket_in=ticket_in, current_user=owner)
        tickets_created += 1

        # Advance workflow
        if t_spec.get("assign_to_agent"):
            # Assigning to agent automatically transitions OPEN -> IN_PROGRESS
            ticket = assign_ticket(
                session,
                ticket_id=ticket.id,
                assign_in=TicketAssign(assignee_id=agent_user.id),
                current_user=admin_user,
            )

        # Add comments before potential status changes to CLOSED
        for c_spec in t_spec.get("comments", []):
            author = users_by_email[c_spec["author_email"]]
            create_comment(
                session,
                ticket_id=ticket.id,
                comment_in=CommentCreate(
                    body=c_spec["body"],
                    is_internal=c_spec["is_internal"],
                ),
                current_user=author,
            )
            comments_created += 1

        # Transition to final status if needed
        final_status = t_spec["final_status"]
        if final_status == TicketStatus.WAITING_ON_REQUESTER:
            ticket = update_ticket_status(
                session,
                ticket_id=ticket.id,
                status_in=TicketStatusUpdate(status=TicketStatus.WAITING_ON_REQUESTER),
                current_user=agent_user,
            )
        elif final_status == TicketStatus.RESOLVED:
            ticket = update_ticket_status(
                session,
                ticket_id=ticket.id,
                status_in=TicketStatusUpdate(status=TicketStatus.RESOLVED),
                current_user=agent_user,
            )
        elif final_status == TicketStatus.CLOSED:
            # Transition to resolved first, then closed
            ticket = update_ticket_status(
                session,
                ticket_id=ticket.id,
                status_in=TicketStatusUpdate(status=TicketStatus.RESOLVED),
                current_user=agent_user,
            )
            ticket = update_ticket_status(
                session,
                ticket_id=ticket.id,
                status_in=TicketStatusUpdate(status=TicketStatus.CLOSED),
                current_user=admin_user,
            )

        # Make unresolved ticket overdue if requested
        # Clearly commented as demo data: manually set due_at in the past
        # to simulate overdue SLA conditions for analytics reports and dashboard.
        if t_spec.get("is_overdue") and t_spec.get("overdue_delta"):
            ticket.due_at = now - t_spec["overdue_delta"]
            session.commit()
            overdue_count += 1

    summary = {
        "users_created": users_created,
        "users_existing": users_existing,
        "tickets_created": tickets_created,
        "tickets_skipped": tickets_skipped,
        "comments_created": comments_created,
        "overdue_tickets": overdue_count,
    }

    _print_summary(summary)
    return summary


def _print_summary(summary: dict[str, int]) -> None:
    print("=" * 60)
    print("HelpDesk API Demo Data Seeding Summary")
    print("=" * 60)
    print("Users:")
    print(f"  - Created:  {summary['users_created']}")
    print(f"  - Existing: {summary['users_existing']}")
    print("Tickets:")
    print(f"  - Created:  {summary['tickets_created']}")
    print(f"  - Skipped:  {summary['tickets_skipped']}")
    print("Comments:")
    print(f"  - Created:  {summary['comments_created']}")
    print("Overdue SLA Tickets Marked:")
    print(f"  - Total:    {summary['overdue_tickets']}")
    print("-" * 60)
    print("Demo Accounts (Known Passwords):")
    print("  - Admin:     admin@example.com     / AdminPassword123!")
    print("  - Agent:     agent@example.com     / AgentPassword123!")
    print("  - Requester: requester@example.com / RequesterPassword123!")
    print("=" * 60)
    print("WARNING: Demo accounts use known passwords and must NEVER")
    print("be deployed or enabled in a production environment!")
    print("=" * 60)


def seed_demo(
    db: Optional[Session] = None,
    allow_seed: bool = False,
) -> dict[str, int]:
    """
    Seed demo users, tickets, comments, and SLA breaches into the database.
    Requires ALLOW_DEMO_SEED=1 in environment or allow_seed=True.
    """
    env_allowed = os.getenv("ALLOW_DEMO_SEED") == "1"
    if not (allow_seed or env_allowed):
        raise RuntimeError(
            "Demo seed refused: ALLOW_DEMO_SEED environment variable must be set to '1' "
            "or --yes passed. Demo accounts use known passwords and must never be used on a real deployment."
        )

    if db is not None:
        return _seed_demo_data(db)
    else:
        with SessionLocal() as session:
            return _seed_demo_data(session)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed HelpDesk API with demo users, tickets, comments, and SLA data."
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Confirm seeding demo accounts with known credentials.",
    )
    args = parser.parse_args()

    allow_seed = args.yes or os.getenv("ALLOW_DEMO_SEED") == "1"
    if not allow_seed:
        print(
            "Refusing to run demo seed:\n"
            "Demo accounts use known credentials and must never be used on a real deployment.\n"
            "To proceed, set the environment variable ALLOW_DEMO_SEED=1 or pass the --yes flag.",
            file=sys.stderr,
        )
        sys.exit(1)

    seed_demo(allow_seed=True)


if __name__ == "__main__":
    main()
