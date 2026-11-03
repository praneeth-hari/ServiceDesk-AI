import argparse
from datetime import date, datetime, time, timedelta, timezone
import os
import sys
from typing import Any, Optional
import zoneinfo
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.core.sla import (
    add_business_minutes,
    business_minutes_between,
    calculate_due_at,
    SLA_HOURS_BY_PRIORITY,
)
from app.db.session import SessionLocal
from app.models.comment import TicketComment
from app.models.embedding import TicketEmbedding
from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.history import TicketStatusHistory
from app.models.ticket import Ticket
from app.models.user import User
from app.services.holidays import get_holiday_dates
from app.services.triage import sync_ticket_embedding
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


def _get_time_from_str(t_str: str) -> time:
    parts = [int(p) for p in t_str.split(":")]
    return time(parts[0], parts[1])


def subtract_business_minutes(
    end_utc: datetime,
    minutes: int,
    holidays: set[date],
) -> datetime:
    """
    Subtract business minutes from end_utc respecting configured operational hours
    (09:00 - 18:00 IST), weekends, and public holidays.
    """
    tz = zoneinfo.ZoneInfo(settings.WORK_TIMEZONE)
    start_t = _get_time_from_str(settings.WORK_DAY_START)
    end_t = _get_time_from_str(settings.WORK_DAY_END)
    cur_dt = end_utc.astimezone(tz)

    # Clamp cur_dt to business window
    while cur_dt.date().weekday() not in settings.WORK_DAYS or cur_dt.date() in holidays:
        cur_dt = datetime.combine(cur_dt.date() - timedelta(days=1), end_t, tzinfo=tz)
    if cur_dt.time() > end_t:
        cur_dt = datetime.combine(cur_dt.date(), end_t, tzinfo=tz)
    elif cur_dt.time() < start_t:
        cur_d = cur_dt.date() - timedelta(days=1)
        while cur_d.weekday() not in settings.WORK_DAYS or cur_d in holidays:
            cur_d -= timedelta(days=1)
        cur_dt = datetime.combine(cur_d, end_t, tzinfo=tz)

    rem_min = minutes
    while rem_min > 0:
        day_start = datetime.combine(cur_dt.date(), start_t, tzinfo=tz)
        avail_min = int((cur_dt - day_start).total_seconds() / 60)
        if rem_min <= avail_min:
            cur_dt = cur_dt - timedelta(minutes=rem_min)
            rem_min = 0
            break
        rem_min -= avail_min
        prev_d = cur_dt.date() - timedelta(days=1)
        while prev_d.weekday() not in settings.WORK_DAYS or prev_d in holidays:
            prev_d -= timedelta(days=1)
        cur_dt = datetime.combine(prev_d, end_t, tzinfo=tz)

    return cur_dt.astimezone(timezone.utc)


def get_demo_ticket_blueprints(
    now: datetime,
    holidays: set[date],
) -> list[dict[str, Any]]:
    """
    Build 16 demo ticket definitions relative to `now`.
    Covers all 7 required SLA/lifecycle states across all priorities and categories:
    1. On Track (5 tickets: plenty of time left)
    2. At Risk (2 tickets: <25% of time left, >=75% elapsed)
    3. Breached (2 tickets: active, past due_at)
    4. Paused (2 tickets: waiting_on_requester with sla_paused_at set, due_at consistent)
    5. Resolved within SLA (2 tickets: resolved_at <= due_at)
    6. Resolved late (2 tickets: resolved_at > due_at)
    7. Closed (1 ticket: resolved within SLA, closed)
    """
    # 1. Very recent created today (Low, on track, assigned to agent)
    t1_created = now - timedelta(minutes=30)
    t1_due = calculate_due_at(TicketPriority.LOW, t1_created, holidays)

    # 2. Active Unassigned #1 (Medium, on track, unassigned)
    t2_created = subtract_business_minutes(now, 180, holidays)
    t2_due = calculate_due_at(TicketPriority.MEDIUM, t2_created, holidays)

    # 3. Active Unassigned #2 (Low, on track, unassigned)
    t3_created = subtract_business_minutes(now, 480, holidays)
    t3_due = calculate_due_at(TicketPriority.LOW, t3_created, holidays)

    # 4. Active On Track #1 (High, plenty of time left)
    t4_created = subtract_business_minutes(now, 120, holidays)
    t4_due = calculate_due_at(TicketPriority.HIGH, t4_created, holidays)

    # 5. Active On Track #2 (Medium, plenty of time left)
    t5_created = subtract_business_minutes(now, 360, holidays)
    t5_due = calculate_due_at(TicketPriority.MEDIUM, t5_created, holidays)

    # 6. Active At Risk #1 (High, 8h = 480m, ~80% elapsed = 385m)
    t6_created = subtract_business_minutes(now, 385, holidays)
    t6_due = calculate_due_at(TicketPriority.HIGH, t6_created, holidays)

    # 7. Active At Risk #2 (Urgent, 2h = 120m, ~82% elapsed = 99m)
    t7_created = subtract_business_minutes(now, 99, holidays)
    t7_due = calculate_due_at(TicketPriority.URGENT, t7_created, holidays)

    # 8. Active Breached #1 (Urgent, created 600 business minutes ago, due was 2h after creation)
    t8_created = subtract_business_minutes(now, 600, holidays)
    t8_due = calculate_due_at(TicketPriority.URGENT, t8_created, holidays)

    # 9. Active Breached #2 (High, created 960 business minutes ago, due was 8h after creation)
    t9_created = subtract_business_minutes(now, 960, holidays)
    t9_due = calculate_due_at(TicketPriority.HIGH, t9_created, holidays)

    # 10. Paused #1 (Medium, waiting_on_requester, paused 2h ago)
    t10_created = subtract_business_minutes(now, 300, holidays)
    t10_due = calculate_due_at(TicketPriority.MEDIUM, t10_created, holidays)
    t10_paused = subtract_business_minutes(now, 120, holidays)

    # 11. Paused #2 (High, waiting_on_requester, paused 1h ago)
    t11_created = subtract_business_minutes(now, 200, holidays)
    t11_due = calculate_due_at(TicketPriority.HIGH, t11_created, holidays)
    t11_paused = subtract_business_minutes(now, 60, holidays)

    # 12. Resolved Within SLA #1 (High, 8h SLA, resolved 3h after creation)
    t12_created = subtract_business_minutes(now, 2400, holidays)
    t12_due = calculate_due_at(TicketPriority.HIGH, t12_created, holidays)
    t12_resolved = add_business_minutes(t12_created, 180, holidays)

    # 13. Resolved Within SLA #2 (Low, 72h SLA, resolved 6h after creation)
    t13_created = subtract_business_minutes(now, 3200, holidays)
    t13_due = calculate_due_at(TicketPriority.LOW, t13_created, holidays)
    t13_resolved = add_business_minutes(t13_created, 360, holidays)

    # 14. Resolved late #1 (Urgent, 2h SLA, resolved 4h after breach)
    t14_created = subtract_business_minutes(now, 2000, holidays)
    t14_due = calculate_due_at(TicketPriority.URGENT, t14_created, holidays)
    t14_resolved = add_business_minutes(t14_due, 240, holidays)

    # 15. Resolved late #2 (High, 8h SLA, resolved 6h after breach)
    t15_created = subtract_business_minutes(now, 2800, holidays)
    t15_due = calculate_due_at(TicketPriority.HIGH, t15_created, holidays)
    t15_resolved = add_business_minutes(t15_due, 360, holidays)

    # 16. Closed Ticket (Medium, resolved within SLA, closed next day)
    t16_created = subtract_business_minutes(now, 3500, holidays)
    t16_due = calculate_due_at(TicketPriority.MEDIUM, t16_created, holidays)
    t16_resolved = add_business_minutes(t16_created, 480, holidays)
    t16_closed = add_business_minutes(t16_resolved, 480, holidays)

    # Historical tickets 17-36 (20 additional historical tickets over the last 3 weeks)
    # 17. Related to #8 (Network / Urgent - core switch boot loop)
    t17_created = subtract_business_minutes(now, 3800, holidays)
    t17_due = calculate_due_at(TicketPriority.URGENT, t17_created, holidays)
    t17_resolved = add_business_minutes(t17_created, 60, holidays)

    # 18. Related to #4 (Network / High - Tokyo VPN gateway slowness)
    t18_created = subtract_business_minutes(now, 4000, holidays)
    t18_due = calculate_due_at(TicketPriority.HIGH, t18_created, holidays)
    t18_resolved = add_business_minutes(t17_created, 180, holidays)

    # 19. Related to #7 (Access / Urgent - SAML SSO login failure)
    t19_created = subtract_business_minutes(now, 4200, holidays)
    t19_due = calculate_due_at(TicketPriority.URGENT, t19_created, holidays)
    t19_resolved = add_business_minutes(t19_due, 180, holidays) # resolved late

    # 20. Related to #15 (Email / High - Mailbox storage quota)
    t20_created = subtract_business_minutes(now, 4500, holidays)
    t20_due = calculate_due_at(TicketPriority.HIGH, t20_created, holidays)
    t20_resolved = add_business_minutes(t20_created, 240, holidays)

    # 21. Hardware / High - Battery swelling (resolved late)
    t21_created = subtract_business_minutes(now, 4700, holidays)
    t21_due = calculate_due_at(TicketPriority.HIGH, t21_created, holidays)
    t21_resolved = add_business_minutes(t21_due, 120, holidays)

    # 22. Software / Urgent - PostgreSQL connection pool (resolved within SLA)
    t22_created = subtract_business_minutes(now, 5000, holidays)
    t22_due = calculate_due_at(TicketPriority.URGENT, t22_created, holidays)
    t22_resolved = add_business_minutes(t22_created, 90, holidays)

    # 23. Software / Medium - SSL certificate expiration (closed)
    t23_created = subtract_business_minutes(now, 5200, holidays)
    t23_due = calculate_due_at(TicketPriority.MEDIUM, t23_created, holidays)
    t23_resolved = add_business_minutes(t23_created, 300, holidays)
    t23_closed = add_business_minutes(t23_resolved, 480, holidays)

    # 24. Hardware / Low - Developer workstation setup (resolved within SLA)
    t24_created = subtract_business_minutes(now, 5400, holidays)
    t24_due = calculate_due_at(TicketPriority.LOW, t24_created, holidays)
    t24_resolved = add_business_minutes(t24_created, 600, holidays)

    # 25. Access / Medium - GitHub enterprise invite (resolved late)
    t25_created = subtract_business_minutes(now, 5700, holidays)
    t25_due = calculate_due_at(TicketPriority.MEDIUM, t25_created, holidays)
    t25_resolved = add_business_minutes(t25_due, 180, holidays)

    # 26. Email / Low - Phishing report false alarm (closed)
    t26_created = subtract_business_minutes(now, 5900, holidays)
    t26_due = calculate_due_at(TicketPriority.LOW, t26_created, holidays)
    t26_resolved = add_business_minutes(t26_created, 480, holidays)
    t26_closed = add_business_minutes(t26_resolved, 300, holidays)

    # 27. Hardware / Medium - Conference room display (resolved within SLA)
    t27_created = subtract_business_minutes(now, 6200, holidays)
    t27_due = calculate_due_at(TicketPriority.MEDIUM, t27_created, holidays)
    t27_resolved = add_business_minutes(t27_created, 240, holidays)

    # 28. Software / High - Kubernetes ingress crashloop (resolved late)
    t28_created = subtract_business_minutes(now, 6400, holidays)
    t28_due = calculate_due_at(TicketPriority.HIGH, t28_created, holidays)
    t28_resolved = add_business_minutes(t28_due, 150, holidays)

    # 29. Other / Medium - Offboarding asset recovery (closed)
    t29_created = subtract_business_minutes(now, 6700, holidays)
    t29_due = calculate_due_at(TicketPriority.MEDIUM, t29_created, holidays)
    t29_resolved = add_business_minutes(t29_created, 360, holidays)
    t29_closed = add_business_minutes(t29_resolved, 240, holidays)

    # 30. Network / Medium - Wi-Fi roaming disconnects (resolved within SLA)
    t30_created = subtract_business_minutes(now, 6900, holidays)
    t30_due = calculate_due_at(TicketPriority.MEDIUM, t30_created, holidays)
    t30_resolved = add_business_minutes(t30_created, 420, holidays)

    # 31. Access / Low - Jira service desk license (resolved within SLA)
    t31_created = subtract_business_minutes(now, 7200, holidays)
    t31_due = calculate_due_at(TicketPriority.LOW, t31_created, holidays)
    t31_resolved = add_business_minutes(t31_created, 300, holidays)

    # 32. Email / High - DKIM signature validation (resolved late)
    t32_created = subtract_business_minutes(now, 7400, holidays)
    t32_due = calculate_due_at(TicketPriority.HIGH, t32_created, holidays)
    t32_resolved = add_business_minutes(t32_due, 200, holidays)

    # 33. Hardware / Low - Standing desk motor (closed)
    t33_created = subtract_business_minutes(now, 7600, holidays)
    t33_due = calculate_due_at(TicketPriority.LOW, t33_created, holidays)
    t33_resolved = add_business_minutes(t33_created, 360, holidays)
    t33_closed = add_business_minutes(t33_resolved, 480, holidays)

    # 34. Software / Urgent - Redis memory alert (resolved within SLA)
    t34_created = subtract_business_minutes(now, 7800, holidays)
    t34_due = calculate_due_at(TicketPriority.URGENT, t34_created, holidays)
    t34_resolved = add_business_minutes(t34_created, 60, holidays)

    # 35. Access / High - MFA reset phone replacement (resolved within SLA)
    t35_created = subtract_business_minutes(now, 8000, holidays)
    t35_due = calculate_due_at(TicketPriority.HIGH, t35_created, holidays)
    t35_resolved = add_business_minutes(t35_created, 180, holidays)

    # 36. Hardware / Low - Office printer maintenance (closed)
    t36_created = subtract_business_minutes(now, 8200, holidays)
    t36_due = calculate_due_at(TicketPriority.LOW, t36_created, holidays)
    t36_resolved = add_business_minutes(t36_created, 300, holidays)
    t36_closed = add_business_minutes(t36_resolved, 300, holidays)

    return [
        {
            "num": 1,
            "title": "Request temporary visitor badge for tomorrow",
            "description": "Client visiting our Bangalore office tomorrow at 10 AM. Need guest badge pre-printed and Wi-Fi credentials prepared.",
            "category": TicketCategory.ACCESS,
            "priority": TicketPriority.LOW,
            "created_at": t1_created,
            "due_at": t1_due,
            "status": TicketStatus.IN_PROGRESS,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": None,
            "closed_at": None,
            "expected_state": "On Track",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "I will coordinate with reception desk to have visitor pass ready.",
                    "is_internal": False,
                    "created_at": t1_created + timedelta(minutes=10),
                },
            ],
        },
        {
            "num": 2,
            "title": "Need access to AWS staging cluster",
            "description": "Requesting read-only kubectl access to the staging EKS cluster for QA regression verification.",
            "category": TicketCategory.ACCESS,
            "priority": TicketPriority.MEDIUM,
            "created_at": t2_created,
            "due_at": t2_due,
            "status": TicketStatus.OPEN,
            "assign_to_agent": False,
            "sla_paused_at": None,
            "resolved_at": None,
            "closed_at": None,
            "expected_state": "On Track",
            "comments": [
                {
                    "author": "requester@example.com",
                    "body": "Manager approved via email request #849.",
                    "is_internal": False,
                    "created_at": t2_created + timedelta(minutes=15),
                },
            ],
        },
        {
            "num": 3,
            "title": "Ergonomic chair request for workstation 4B",
            "description": "Current chair has broken lumbar support cylinder and cannot be locked upright.",
            "category": TicketCategory.HARDWARE,
            "priority": TicketPriority.LOW,
            "created_at": t3_created,
            "due_at": t3_due,
            "status": TicketStatus.OPEN,
            "assign_to_agent": False,
            "sla_paused_at": None,
            "resolved_at": None,
            "closed_at": None,
            "expected_state": "On Track",
            "comments": [
                {
                    "author": "requester@example.com",
                    "body": "Workstation is 4B in the east wing.",
                    "is_internal": False,
                    "created_at": t3_created + timedelta(minutes=20),
                },
            ],
        },
        {
            "num": 4,
            "title": "Slow VPN connectivity on Tokyo gateway",
            "description": "Experiencing high packet latency (>280ms) and occasional drops on the Tokyo gateway.",
            "category": TicketCategory.NETWORK,
            "priority": TicketPriority.HIGH,
            "created_at": t4_created,
            "due_at": t4_due,
            "status": TicketStatus.IN_PROGRESS,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": None,
            "closed_at": None,
            "expected_state": "On Track",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Investigating routing table on AP-Northeast edge routers.",
                    "is_internal": False,
                    "created_at": t4_created + timedelta(minutes=25),
                },
                {
                    "author": "agent@example.com",
                    "body": "Looks like NTT transit link congestion. Opening upstream ticket.",
                    "is_internal": True,
                    "created_at": t4_created + timedelta(minutes=45),
                },
            ],
        },
        {
            "num": 5,
            "title": "Docker Desktop license renewal request",
            "description": "Annual Docker Desktop commercial license seat expires next week.",
            "category": TicketCategory.SOFTWARE,
            "priority": TicketPriority.MEDIUM,
            "created_at": t5_created,
            "due_at": t5_due,
            "status": TicketStatus.IN_PROGRESS,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": None,
            "closed_at": None,
            "expected_state": "On Track",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Processing bulk license renewal through procurement.",
                    "is_internal": False,
                    "created_at": t5_created + timedelta(minutes=30),
                },
                {
                    "author": "requester@example.com",
                    "body": "Thanks, please let me know once key is generated.",
                    "is_internal": False,
                    "created_at": t5_created + timedelta(minutes=60),
                },
            ],
        },
        {
            "num": 6,
            "title": "Monitor flickering on executive boardroom display",
            "description": "Primary 85-inch presentation display in boardroom A flickers every few minutes over HDMI.",
            "category": TicketCategory.HARDWARE,
            "priority": TicketPriority.HIGH,
            "created_at": t6_created,
            "due_at": t6_due,
            "status": TicketStatus.IN_PROGRESS,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": None,
            "closed_at": None,
            "expected_state": "At Risk",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Tested with alternate HDMI 2.1 cable; issue persists.",
                    "is_internal": False,
                    "created_at": t6_created + timedelta(minutes=40),
                },
                {
                    "author": "agent@example.com",
                    "body": "Display scaler board might be overheating. Calling AV vendor technician.",
                    "is_internal": True,
                    "created_at": t6_created + timedelta(minutes=80),
                },
                {
                    "author": "requester@example.com",
                    "body": "Board meeting starts this afternoon, urgent fix appreciated.",
                    "is_internal": False,
                    "created_at": t6_created + timedelta(minutes=110),
                },
            ],
        },
        {
            "num": 7,
            "title": "SSO login failure for financial reporting tool",
            "description": "Finance team members encountering SAML assertion error 400 when logging into NetSuite.",
            "category": TicketCategory.ACCESS,
            "priority": TicketPriority.URGENT,
            "created_at": t7_created,
            "due_at": t7_due,
            "status": TicketStatus.IN_PROGRESS,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": None,
            "closed_at": None,
            "expected_state": "At Risk",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Okta metadata certificate expired this morning. Regenerating certificate.",
                    "is_internal": True,
                    "created_at": t7_created + timedelta(minutes=15),
                },
                {
                    "author": "agent@example.com",
                    "body": "Uploading new signing certificate to NetSuite SAML configuration now.",
                    "is_internal": False,
                    "created_at": t7_created + timedelta(minutes=35),
                },
            ],
        },
        {
            "num": 8,
            "title": "Core switch rebooting continuously in server room B",
            "description": "Cisco Catalyst core switch in rack 3 is stuck in a boot loop affecting dev lab subnets.",
            "category": TicketCategory.NETWORK,
            "priority": TicketPriority.URGENT,
            "created_at": t8_created,
            "due_at": t8_due,
            "status": TicketStatus.IN_PROGRESS,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": None,
            "closed_at": None,
            "expected_state": "Breached",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Console cable connected; switch reporting corrupted IOS image in boot flash.",
                    "is_internal": True,
                    "created_at": t8_created + timedelta(minutes=30),
                },
                {
                    "author": "requester@example.com",
                    "body": "Dev team cannot access local testing environments.",
                    "is_internal": False,
                    "created_at": t8_created + timedelta(minutes=60),
                },
                {
                    "author": "agent@example.com",
                    "body": "TFTP recovery in progress with Cisco TAC engineer on bridge.",
                    "is_internal": False,
                    "created_at": t8_created + timedelta(minutes=90),
                },
            ],
        },
        {
            "num": 9,
            "title": "Company-wide newsletter bouncing with SPF failure",
            "description": "Quarterly update emails sent via marketing platform are failing SPF authentication.",
            "category": TicketCategory.EMAIL,
            "priority": TicketPriority.HIGH,
            "created_at": t9_created,
            "due_at": t9_due,
            "status": TicketStatus.IN_PROGRESS,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": None,
            "closed_at": None,
            "expected_state": "Breached",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Discovered new ESP sending IP was omitted from TXT record include mechanism.",
                    "is_internal": True,
                    "created_at": t9_created + timedelta(minutes=45),
                },
                {
                    "author": "agent@example.com",
                    "body": "Updated DNS TXT record; awaiting TTL expiration across public nameservers.",
                    "is_internal": False,
                    "created_at": t9_created + timedelta(minutes=90),
                },
            ],
        },
        {
            "num": 10,
            "title": "GitLab CI runner timeout on large monorepo build",
            "description": "Docker executor times out after 60 minutes on mobile app compilation jobs.",
            "category": TicketCategory.SOFTWARE,
            "priority": TicketPriority.MEDIUM,
            "created_at": t10_created,
            "due_at": t10_due,
            "status": TicketStatus.WAITING_ON_REQUESTER,
            "assign_to_agent": True,
            "sla_paused_at": t10_paused,
            "resolved_at": None,
            "closed_at": None,
            "expected_state": "Paused",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Could you provide the full job trace log and the .gitlab-ci.yml runner tags?",
                    "is_internal": False,
                    "created_at": t10_created + timedelta(minutes=45),
                },
                {
                    "author": "agent@example.com",
                    "body": "Suspect runner disk cache is saturated or CPU throttled.",
                    "is_internal": True,
                    "created_at": t10_created + timedelta(minutes=75),
                },
            ],
        },
        {
            "num": 11,
            "title": "Permission denied accessing production customer analytics",
            "description": "Cannot query BigQuery analytics datasets for monthly cohort reporting.",
            "category": TicketCategory.ACCESS,
            "priority": TicketPriority.HIGH,
            "created_at": t11_created,
            "due_at": t11_due,
            "status": TicketStatus.WAITING_ON_REQUESTER,
            "assign_to_agent": True,
            "sla_paused_at": t11_paused,
            "resolved_at": None,
            "closed_at": None,
            "expected_state": "Paused",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Please submit Manager approval form SD-402 so IAM roles can be granted.",
                    "is_internal": False,
                    "created_at": t11_created + timedelta(minutes=30),
                },
                {
                    "author": "agent@example.com",
                    "body": "Pending compliance approval for PII access tier.",
                    "is_internal": True,
                    "created_at": t11_created + timedelta(minutes=50),
                },
            ],
        },
        {
            "num": 12,
            "title": "Keyboard replacement for damaged laptop keys",
            "description": "Spilled water on external mechanical keyboard; spacebar and enter keys unresponsive.",
            "category": TicketCategory.HARDWARE,
            "priority": TicketPriority.HIGH,
            "created_at": t12_created,
            "due_at": t12_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t12_resolved,
            "closed_at": None,
            "expected_state": "Resolved within SLA",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Issued new replacement mechanical keyboard from IT inventory.",
                    "is_internal": False,
                    "created_at": t12_created + timedelta(hours=2),
                },
                {
                    "author": "requester@example.com",
                    "body": "Received and confirmed working perfectly. Thank you!",
                    "is_internal": False,
                    "created_at": t12_resolved,
                },
            ],
        },
        {
            "num": 13,
            "title": "Security pass replacement for contractor",
            "description": "Contractor RFID badge lost over the weekend. Needs new temporary access card.",
            "category": TicketCategory.OTHER,
            "priority": TicketPriority.LOW,
            "created_at": t13_created,
            "due_at": t13_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t13_resolved,
            "closed_at": None,
            "expected_state": "Resolved within SLA",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Deactivated lost card #4092 and encoded new contractor badge #5120.",
                    "is_internal": True,
                    "created_at": t13_created + timedelta(hours=3),
                },
                {
                    "author": "agent@example.com",
                    "body": "Badge ready at reception security desk.",
                    "is_internal": False,
                    "created_at": t13_resolved,
                },
            ],
        },
        {
            "num": 14,
            "title": "Primary DNS server unresponsive during office hours",
            "description": "Internal recursive DNS resolver stopped responding to queries from VLAN 10.",
            "category": TicketCategory.NETWORK,
            "priority": TicketPriority.URGENT,
            "created_at": t14_created,
            "due_at": t14_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t14_resolved,
            "closed_at": None,
            "expected_state": "Resolved late",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Core dump analysis showed named process memory leak on BIND 9.18.",
                    "is_internal": True,
                    "created_at": t14_created + timedelta(hours=3),
                },
                {
                    "author": "agent@example.com",
                    "body": "Patched to 9.18.19 and verified query latency under 2ms.",
                    "is_internal": False,
                    "created_at": t14_resolved,
                },
            ],
        },
        {
            "num": 15,
            "title": "Executive mailbox quota exceeded warning",
            "description": "CFO mailbox reached 99% capacity, preventing calendar invites and incoming attachments.",
            "category": TicketCategory.EMAIL,
            "priority": TicketPriority.HIGH,
            "created_at": t15_created,
            "due_at": t15_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t15_resolved,
            "closed_at": None,
            "expected_state": "Resolved late",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Archived emails older than 2 years to compliance vault and expanded mailbox quota to 100GB.",
                    "is_internal": False,
                    "created_at": t15_created + timedelta(hours=5),
                },
                {
                    "author": "agent@example.com",
                    "body": "Retention policy updated in Exchange Admin Center.",
                    "is_internal": True,
                    "created_at": t15_resolved,
                },
            ],
        },
        {
            "num": 16,
            "title": "Python environment conflict on shared dev server",
            "description": "PyTorch and CUDA driver version mismatch on GPU server 2 broke training scripts.",
            "category": TicketCategory.SOFTWARE,
            "priority": TicketPriority.MEDIUM,
            "created_at": t16_created,
            "due_at": t16_due,
            "status": TicketStatus.CLOSED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t16_resolved,
            "closed_at": t16_closed,
            "expected_state": "Closed",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Re-installed CUDA 12.1 toolkit and rebuilt PyTorch virtualenv.",
                    "is_internal": False,
                    "created_at": t16_created + timedelta(hours=4),
                },
                {
                    "author": "requester@example.com",
                    "body": "Training runs completed without errors.",
                    "is_internal": False,
                    "created_at": t16_resolved,
                },
                {
                    "author": "admin@example.com",
                    "body": "Closing ticket following user confirmation.",
                    "is_internal": True,
                    "created_at": t16_closed,
                },
            ],
        },
        {
            "num": 17,
            "title": "Core switch boot loop after firmware upgrade in server room B",
            "description": "Cisco Catalyst core switch in server room B stuck in reboot loop following 17.06 IOS upgrade affecting engineering VLAN.",
            "category": TicketCategory.NETWORK,
            "priority": TicketPriority.URGENT,
            "created_at": t17_created,
            "due_at": t17_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t17_resolved,
            "closed_at": None,
            "expected_state": "Resolved within SLA",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Connected console rollover cable. Boot flash contained corrupted microcode binary.",
                    "is_internal": True,
                    "created_at": t17_created + timedelta(minutes=20),
                },
                {
                    "author": "agent@example.com",
                    "body": "Restored golden IOS release image via TFTP and verified STP convergence.",
                    "is_internal": False,
                    "created_at": t17_resolved,
                },
            ],
        },
        {
            "num": 18,
            "title": "High latency and packet loss on Tokyo VPN gateway",
            "description": "Tokyo VPN gateway tunnel degradation and packet loss affecting APAC remote staff accessing code repositories.",
            "category": TicketCategory.NETWORK,
            "priority": TicketPriority.HIGH,
            "created_at": t18_created,
            "due_at": t18_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t18_resolved,
            "closed_at": None,
            "expected_state": "Resolved within SLA",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Upstream NTT transit provider reported underwater fiber cut near Okinawa.",
                    "is_internal": True,
                    "created_at": t18_created + timedelta(minutes=45),
                },
                {
                    "author": "agent@example.com",
                    "body": "Rerouted IPsec tunnel traffic via secondary Osaka peering gateway.",
                    "is_internal": False,
                    "created_at": t18_resolved,
                },
            ],
        },
        {
            "num": 19,
            "title": "SAML SSO authentication failure on NetSuite financial portal",
            "description": "Finance users receiving SAML response status invalid on NetSuite SSO login via Okta identity provider.",
            "category": TicketCategory.ACCESS,
            "priority": TicketPriority.URGENT,
            "created_at": t19_created,
            "due_at": t19_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t19_resolved,
            "closed_at": None,
            "expected_state": "Resolved late",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Okta signing certificate rotated automatically without updating NetSuite metadata.",
                    "is_internal": True,
                    "created_at": t19_created + timedelta(minutes=30),
                },
                {
                    "author": "agent@example.com",
                    "body": "Manually uploaded SHA256 X.509 certificate to NetSuite SAML setup.",
                    "is_internal": False,
                    "created_at": t19_resolved,
                },
            ],
        },
        {
            "num": 20,
            "title": "Mailbox storage quota exceeded for VP of Engineering",
            "description": "Executive mailbox reached capacity limit with bouncing calendar invitations and attachments.",
            "category": TicketCategory.EMAIL,
            "priority": TicketPriority.HIGH,
            "created_at": t20_created,
            "due_at": t20_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t20_resolved,
            "closed_at": None,
            "expected_state": "Resolved within SLA",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Provisioned Exchange Online Plan 2 license with 100GB mailbox quota.",
                    "is_internal": False,
                    "created_at": t20_resolved,
                },
            ],
        },
        {
            "num": 21,
            "title": "MacBook Pro battery swelling and trackpad bulge",
            "description": "Developer laptop battery expanding, causing trackpad click mechanism to fail.",
            "category": TicketCategory.HARDWARE,
            "priority": TicketPriority.HIGH,
            "created_at": t21_created,
            "due_at": t21_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t21_resolved,
            "closed_at": None,
            "expected_state": "Resolved late",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Safety hazard flagged. Swapped user to loaner laptop and sent unit to Apple Authorized repair.",
                    "is_internal": False,
                    "created_at": t21_resolved,
                },
            ],
        },
        {
            "num": 22,
            "title": "Production PostgreSQL connection pool exhaustion",
            "description": "PgBouncer pool saturated with idle connections during payment processing batch.",
            "category": TicketCategory.SOFTWARE,
            "priority": TicketPriority.URGENT,
            "created_at": t22_created,
            "due_at": t22_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t22_resolved,
            "closed_at": None,
            "expected_state": "Resolved within SLA",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Terminated orphaned backend transactions and increased max_client_conn parameter.",
                    "is_internal": False,
                    "created_at": t22_resolved,
                },
            ],
        },
        {
            "num": 23,
            "title": "SSL certificate expiration on internal wiki documentation",
            "description": "Let's Encrypt renewal hook failed on Confluence internal wiki host.",
            "category": TicketCategory.SOFTWARE,
            "priority": TicketPriority.MEDIUM,
            "created_at": t23_created,
            "due_at": t23_due,
            "status": TicketStatus.CLOSED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t23_resolved,
            "closed_at": t23_closed,
            "expected_state": "Closed",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Fixed certbot route53 credentials and reloaded nginx proxy.",
                    "is_internal": False,
                    "created_at": t23_resolved,
                },
                {
                    "author": "admin@example.com",
                    "body": "Verified HTTPS padlock and closed ticket.",
                    "is_internal": True,
                    "created_at": t23_closed,
                },
            ],
        },
        {
            "num": 24,
            "title": "New hire developer workstation provisioning for QA team",
            "description": "Need standard Ubuntu workstation setup with Docker, VS Code, and VPN credentials.",
            "category": TicketCategory.HARDWARE,
            "priority": TicketPriority.LOW,
            "created_at": t24_created,
            "due_at": t24_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t24_resolved,
            "closed_at": None,
            "expected_state": "Resolved within SLA",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Dell Precision workstation imaged via PXE boot and placed on QA desk 8.",
                    "is_internal": False,
                    "created_at": t24_resolved,
                },
            ],
        },
        {
            "num": 25,
            "title": "GitHub enterprise organization invite not received",
            "description": "Contractor cannot accept invitation to private repositories for frontend project.",
            "category": TicketCategory.ACCESS,
            "priority": TicketPriority.MEDIUM,
            "created_at": t25_created,
            "due_at": t25_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t25_resolved,
            "closed_at": None,
            "expected_state": "Resolved late",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Resent invitation to verified corporate email and verified 2FA compliance.",
                    "is_internal": False,
                    "created_at": t25_resolved,
                },
            ],
        },
        {
            "num": 26,
            "title": "Phishing simulation email report false alarm",
            "description": "Security team annual awareness campaign caught multiple employees reporting real newsletter.",
            "category": TicketCategory.EMAIL,
            "priority": TicketPriority.LOW,
            "created_at": t26_created,
            "due_at": t26_due,
            "status": TicketStatus.CLOSED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t26_resolved,
            "closed_at": t26_closed,
            "expected_state": "Closed",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Confirmed message was legitimate marketing update. Whitelisted sender in Proofpoint.",
                    "is_internal": False,
                    "created_at": t26_resolved,
                },
            ],
        },
        {
            "num": 27,
            "title": "Conference room display audio distorted during all-hands",
            "description": "HDMI and Polycom ceiling mic echoing in 5th floor boardroom.",
            "category": TicketCategory.HARDWARE,
            "priority": TicketPriority.MEDIUM,
            "created_at": t27_created,
            "due_at": t27_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t27_resolved,
            "closed_at": None,
            "expected_state": "Resolved within SLA",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Rebooted DSP audio mixer and updated firmware on Zoom Room controller.",
                    "is_internal": False,
                    "created_at": t27_resolved,
                },
            ],
        },
        {
            "num": 28,
            "title": "Kubernetes pod crashloop backoff on staging ingress",
            "description": "Nginx ingress controller crashing after cert-manager configmap schema change.",
            "category": TicketCategory.SOFTWARE,
            "priority": TicketPriority.HIGH,
            "created_at": t28_created,
            "due_at": t28_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t28_resolved,
            "closed_at": None,
            "expected_state": "Resolved late",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Rolled back ingress-nginx Helm release to v1.9.4 and restored staging traffic.",
                    "is_internal": False,
                    "created_at": t28_resolved,
                },
            ],
        },
        {
            "num": 29,
            "title": "Offboarding asset recovery and account suspension",
            "description": "Employee departure checklist: revoke Google Workspace, AWS IAM, and retrieve badge.",
            "category": TicketCategory.OTHER,
            "priority": TicketPriority.MEDIUM,
            "created_at": t29_created,
            "due_at": t29_due,
            "status": TicketStatus.CLOSED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t29_resolved,
            "closed_at": t29_closed,
            "expected_state": "Closed",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "All accounts deprovisioned and security keys retrieved.",
                    "is_internal": True,
                    "created_at": t29_resolved,
                },
            ],
        },
        {
            "num": 30,
            "title": "Wi-Fi roaming disconnects between 3rd and 4th floors",
            "description": "Aruba AP handover failure drops Slack calls while walking between buildings.",
            "category": TicketCategory.NETWORK,
            "priority": TicketPriority.MEDIUM,
            "created_at": t30_created,
            "due_at": t30_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t30_resolved,
            "closed_at": None,
            "expected_state": "Resolved within SLA",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Adjusted 802.11k/r neighbor report thresholds and 5GHz transmit power on stairwell APs.",
                    "is_internal": False,
                    "created_at": t30_resolved,
                },
            ],
        },
        {
            "num": 31,
            "title": "Jira software service desk license allocation",
            "description": "Need agent seat assigned to new Tier 2 support engineer joining next Monday.",
            "category": TicketCategory.ACCESS,
            "priority": TicketPriority.LOW,
            "created_at": t31_created,
            "due_at": t31_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t31_resolved,
            "closed_at": None,
            "expected_state": "Resolved within SLA",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Allocated Atlassian Access license and assigned to Service Desk Agents group.",
                    "is_internal": False,
                    "created_at": t31_resolved,
                },
            ],
        },
        {
            "num": 32,
            "title": "DKIM signature validation failure on transactional emails",
            "description": "SendGrid transactional receipts failing DMARC alignment due to selector rotation.",
            "category": TicketCategory.EMAIL,
            "priority": TicketPriority.HIGH,
            "created_at": t32_created,
            "due_at": t32_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t32_resolved,
            "closed_at": None,
            "expected_state": "Resolved late",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Published CNAME record for new s1 selector in Cloudflare DNS.",
                    "is_internal": False,
                    "created_at": t32_resolved,
                },
            ],
        },
        {
            "num": 33,
            "title": "Standing desk motor unresponsive on workstation 12C",
            "description": "Height adjustable desk stuck at maximum height with error code E08.",
            "category": TicketCategory.HARDWARE,
            "priority": TicketPriority.LOW,
            "created_at": t33_created,
            "due_at": t33_due,
            "status": TicketStatus.CLOSED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t33_resolved,
            "closed_at": t33_closed,
            "expected_state": "Closed",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Performed manual reset sequence (hold down for 10s). Desk operating smoothly.",
                    "is_internal": False,
                    "created_at": t33_resolved,
                },
            ],
        },
        {
            "num": 34,
            "title": "Redis cluster high memory fragmentation alert",
            "description": "Session store Redis node 3 memory usage exceeded 90% threshold during flash sale.",
            "category": TicketCategory.SOFTWARE,
            "priority": TicketPriority.URGENT,
            "created_at": t34_created,
            "due_at": t34_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t34_resolved,
            "closed_at": None,
            "expected_state": "Resolved within SLA",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Enabled active defragmentation and flushed expired session keys.",
                    "is_internal": False,
                    "created_at": t34_resolved,
                },
            ],
        },
        {
            "num": 35,
            "title": "Multi-factor authentication reset for mobile phone replacement",
            "description": "Employee got new phone and lost Google Authenticator seeds for corporate Google account.",
            "category": TicketCategory.ACCESS,
            "priority": TicketPriority.HIGH,
            "created_at": t35_created,
            "due_at": t35_due,
            "status": TicketStatus.RESOLVED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t35_resolved,
            "closed_at": None,
            "expected_state": "Resolved within SLA",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Verified identity via manager Zoom video call and issued temporary 2FA backup codes.",
                    "is_internal": False,
                    "created_at": t35_resolved,
                },
            ],
        },
        {
            "num": 36,
            "title": "Office printer toner replacement and paper jam error",
            "description": "Floor 2 HP LaserJet Enterprise showing maintenance kit required and error 13.00.",
            "category": TicketCategory.HARDWARE,
            "priority": TicketPriority.LOW,
            "created_at": t36_created,
            "due_at": t36_due,
            "status": TicketStatus.CLOSED,
            "assign_to_agent": True,
            "sla_paused_at": None,
            "resolved_at": t36_resolved,
            "closed_at": t36_closed,
            "expected_state": "Closed",
            "comments": [
                {
                    "author": "agent@example.com",
                    "body": "Cleared accordion paper jam in fuser unit and installed fresh high-yield black toner cartridge.",
                    "is_internal": False,
                    "created_at": t36_resolved,
                },
            ],
        },
    ]


def _print_dry_run_table(blueprints: list[dict[str, Any]]) -> None:
    """Print ASCII table showing what would be written."""
    print("=" * 118)
    print("DEMO SEED DRY-RUN SUMMARY TABLE (No changes made to database)")
    print("=" * 118)
    header = f"{'#':<3} | {'Title':<42} | {'Cat':<9} | {'Prio':<7} | {'Status':<21} | {'Assignee':<8} | {'State':<18} | {'Comments'}"
    print(header)
    print("-" * 118)
    state_counts: dict[str, int] = {}
    for b in blueprints:
        assignee = "agent" if b["assign_to_agent"] else "None"
        c_count = len(b["comments"])
        state = b["expected_state"]
        state_counts[state] = state_counts.get(state, 0) + 1
        print(
            f"{b['num']:<3} | {b['title'][:42]:<42} | {b['category'].value:<9} | {b['priority'].value:<7} | {b['status'].value:<21} | {assignee:<8} | {state:<18} | {c_count}"
        )
    print("=" * 118)
    summary_parts = [f"{k}: {v}" for k, v in state_counts.items()]
    print(f"Summary by state: {', '.join(summary_parts)} (Total: {len(blueprints)})")
    print("=" * 118)


def _seed_demo_data(
    session: Session,
    wipe_tickets: bool = False,
    dry_run: bool = False,
    allow_seed: bool = False,
) -> dict[str, Any]:
    """Execute demo data seeding within the given database session."""
    # 1. Handle wipe-tickets safety checks
    if wipe_tickets:
        ticket_count = session.scalar(sa.select(sa.func.count(Ticket.id))) or 0
        comment_count = session.scalar(sa.select(sa.func.count(TicketComment.id))) or 0
        history_count = session.scalar(sa.select(sa.func.count(TicketStatusHistory.id))) or 0

        if not allow_seed:
            print(f"Safety check: --wipe-tickets would delete {ticket_count} tickets, {comment_count} comments, and {history_count} history rows.")
            print("Pass --yes to confirm deletion.")
            return {
                "wiped": False,
                "tickets_deleted": 0,
                "comments_deleted": 0,
                "history_deleted": 0,
                "tickets_would_delete": ticket_count,
            }

        # Confirmed wipe
        session.query(TicketEmbedding).delete()
        session.query(TicketComment).delete()
        session.query(TicketStatusHistory).delete()
        session.query(Ticket).delete()
        session.commit()
        print(f"Wiped {ticket_count} tickets, {comment_count} comments, and {history_count} history rows.")

    now = datetime.now(timezone.utc)
    holidays = get_holiday_dates(session)
    blueprints = get_demo_ticket_blueprints(now, holidays)

    if dry_run:
        _print_dry_run_table(blueprints)
        return {
            "dry_run": True,
            "tickets_planned": len(blueprints),
            "users_created": 0,
            "tickets_created": 0,
        }

    # 2. Ensure demo users exist
    users_by_email: dict[str, User] = {}
    users_created = 0
    users_existing = 0

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
    requester_user = users_by_email["requester@example.com"]

    # 3. Check idempotence: if demo tickets already exist and we are not wiping, do not duplicate
    demo_titles = [b["title"] for b in blueprints]
    existing_demo_tickets = session.scalars(
        sa.select(Ticket).where(Ticket.title.in_(demo_titles))
    ).all()

    if existing_demo_tickets:
        print("demo tickets already present, nothing added")
        summary = {
            "users_created": users_created,
            "users_existing": users_existing,
            "tickets_created": 0,
            "tickets_skipped": len(blueprints),
            "comments_created": 0,
            "already_present": True,
        }
        _print_summary(summary)
        return summary

    tickets_created = 0
    tickets_skipped = 0
    comments_created = 0

    for b in blueprints:
        ticket = Ticket(
            title=b["title"],
            description=b["description"],
            status=b["status"],
            priority=b["priority"],
            category=b["category"],
            requester_id=requester_user.id,
            assignee_id=agent_user.id if b["assign_to_agent"] else None,
            due_at=b["due_at"],
            sla_paused_at=b["sla_paused_at"],
            resolved_at=b["resolved_at"],
            created_at=b["created_at"],
            updated_at=b["closed_at"] or b["resolved_at"] or b["sla_paused_at"] or b["created_at"],
        )
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        sync_ticket_embedding(session, ticket)
        tickets_created += 1

        # Build Status History Entries
        # 1. Creation event
        h_create = TicketStatusHistory(
            ticket_id=ticket.id,
            from_status=None,
            to_status=TicketStatus.OPEN,
            changed_by_id=requester_user.id,
            created_at=b["created_at"],
        )
        session.add(h_create)

        # 2. Assignment / In Progress transition
        if b["assign_to_agent"]:
            assign_time = b["created_at"] + timedelta(minutes=15)
            h_assign = TicketStatusHistory(
                ticket_id=ticket.id,
                from_status=TicketStatus.OPEN,
                to_status=TicketStatus.IN_PROGRESS,
                changed_by_id=agent_user.id,
                created_at=assign_time,
            )
            session.add(h_assign)

        # 3. Paused transition
        if b["status"] == TicketStatus.WAITING_ON_REQUESTER and b["sla_paused_at"]:
            h_pause = TicketStatusHistory(
                ticket_id=ticket.id,
                from_status=TicketStatus.IN_PROGRESS,
                to_status=TicketStatus.WAITING_ON_REQUESTER,
                changed_by_id=agent_user.id,
                created_at=b["sla_paused_at"],
            )
            session.add(h_pause)

        # 4. Resolved transition
        if b["resolved_at"]:
            h_resolved = TicketStatusHistory(
                ticket_id=ticket.id,
                from_status=TicketStatus.IN_PROGRESS,
                to_status=TicketStatus.RESOLVED,
                changed_by_id=agent_user.id,
                created_at=b["resolved_at"],
            )
            session.add(h_resolved)

        # 5. Closed transition
        if b["closed_at"]:
            h_closed = TicketStatusHistory(
                ticket_id=ticket.id,
                from_status=TicketStatus.RESOLVED,
                to_status=TicketStatus.CLOSED,
                changed_by_id=admin_user.id,
                created_at=b["closed_at"],
            )
            session.add(h_closed)

        # Comments
        for c in b["comments"]:
            author = users_by_email[c["author"]]
            comment = TicketComment(
                ticket_id=ticket.id,
                author_id=author.id,
                body=c["body"],
                is_internal=c["is_internal"],
                created_at=c["created_at"],
            )
            session.add(comment)
            comments_created += 1

        session.commit()

    summary = {
        "users_created": users_created,
        "users_existing": users_existing,
        "tickets_created": tickets_created,
        "tickets_skipped": tickets_skipped,
        "comments_created": comments_created,
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
    print("-" * 60)
    print("Demo Accounts (Known Passwords):")
    print("  - Admin:     admin@example.com     / AdminPassword123!")
    print("  - Agent:     agent@example.com     / AgentPassword123!")
    print("  - Requester: requester@example.com / RequesterPassword123!")
    print("=" * 60)


def seed_demo(
    db: Optional[Session] = None,
    wipe_tickets: bool = False,
    dry_run: bool = False,
    allow_seed: bool = False,
) -> dict[str, Any]:
    """
    Seed demo tickets, comments, and status history into the database.
    Requires ALLOW_DEMO_SEED=1 in environment or allow_seed=True (or --yes).
    """
    env_allowed = os.getenv("ALLOW_DEMO_SEED") == "1"
    is_allowed = allow_seed or env_allowed

    # Dry run does not write anything, so it can run freely or check permission
    if not dry_run and not wipe_tickets and not is_allowed:
        raise RuntimeError(
            "Demo seed refused: ALLOW_DEMO_SEED environment variable must be set to '1' "
            "or --yes passed. Demo accounts use known passwords and must never be used on a real deployment."
        )

    if db is not None:
        return _seed_demo_data(
            db,
            wipe_tickets=wipe_tickets,
            dry_run=dry_run,
            allow_seed=is_allowed,
        )
    else:
        with SessionLocal() as session:
            return _seed_demo_data(
                session,
                wipe_tickets=wipe_tickets,
                dry_run=dry_run,
                allow_seed=is_allowed,
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed HelpDesk API with ~16 realistic demo tickets, comments, and SLA states."
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Confirm executing seed or wiping tickets.",
    )
    parser.add_argument(
        "--wipe-tickets",
        action="store_true",
        help="Delete all tickets, comments, and history before seeding (requires --yes).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary table of what would be written without modifying the database.",
    )
    args = parser.parse_args()

    allow_seed = args.yes or os.getenv("ALLOW_DEMO_SEED") == "1"

    if args.dry_run:
        seed_demo(dry_run=True, allow_seed=True)
        return

    if args.wipe_tickets and not allow_seed:
        seed_demo(wipe_tickets=True, allow_seed=False)
        return

    if not allow_seed:
        print(
            "Refusing to run demo seed:\n"
            "Demo accounts use known credentials and must never be used on a real deployment.\n"
            "To proceed, set the environment variable ALLOW_DEMO_SEED=1 or pass the --yes flag.",
            file=sys.stderr,
        )
        sys.exit(1)

    seed_demo(
        wipe_tickets=args.wipe_tickets,
        dry_run=args.dry_run,
        allow_seed=True,
    )


if __name__ == "__main__":
    main()
