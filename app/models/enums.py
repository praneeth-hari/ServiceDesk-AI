import enum


class UserRole(str, enum.Enum):
    REQUESTER = "requester"
    AGENT = "agent"
    ADMIN = "admin"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_ON_REQUESTER = "waiting_on_requester"
    RESOLVED = "resolved"
    CLOSED = "closed"



class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketCategory(str, enum.Enum):
    NETWORK = "network"
    HARDWARE = "hardware"
    SOFTWARE = "software"
    ACCESS = "access"
    EMAIL = "email"
    OTHER = "other"

