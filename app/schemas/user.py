from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole


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


class UserLogin(BaseModel):
    """Schema for user login credentials."""
    email: EmailStr
    password: str


class UserRoleUpdate(BaseModel):
    """Schema for updating a user's role (admin only)."""
    role: UserRole


class UserRead(BaseModel):
    """Safe public schema for user information, never exposing password hashes."""
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
