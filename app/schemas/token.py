from enum import Enum
from pydantic import BaseModel


class Token(BaseModel):
    """Schema for authentication token response."""
    access_token: str
    token_type: str = "bearer"


class DemoRole(str, Enum):
    REQUESTER = "requester"
    AGENT = "agent"
    ADMIN = "admin"


class DemoAccountRead(BaseModel):
    role: str
    name: str
    description: str


class DemoAccountsResponse(BaseModel):
    enabled: bool
    accounts: list[DemoAccountRead]


class DemoLoginRequest(BaseModel):
    role: DemoRole
