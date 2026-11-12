"""Fixed demo account definitions shared by the demo seeder and demo login."""

from app.models.enums import UserRole

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
