from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole
from app.schemas.common import UTCDateTime


class UserCreate(BaseModel):
    """Schema for user registration."""
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password_byte_length(cls, v: str) -> str:
        """Enforce bcrypt's maximum input limit of 72 UTF-8 bytes."""
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password cannot exceed 72 bytes")
        return v


class UserAdminCreate(BaseModel):
    """Schema for admin user creation."""
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    role: UserRole
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password_byte_length(cls, v: str) -> str:
        """Enforce bcrypt's maximum input limit of 72 UTF-8 bytes."""
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password cannot exceed 72 bytes")
        return v


class UserLogin(BaseModel):
    """Schema for user login credentials."""
    email: EmailStr
    password: str


class UserRoleUpdate(BaseModel):
    """Schema for updating a user's role (admin only)."""
    role: UserRole


class UserStatusUpdate(BaseModel):
    """Schema for updating a user's active status (admin only)."""
    is_active: bool


class UserRead(BaseModel):
    """Safe public schema for user information, never exposing password hashes."""
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True)


class UserAdminRead(UserRead):
    """Extended user schema with open assigned ticket metrics."""
    open_assigned_count: int = 0


class UserListResponse(BaseModel):
    """Paginated or filtered list of users with active and total counts."""
    rows: list[UserAdminRead]
    users: list[UserAdminRead]
    total: int
    active_count: int
    active: int
