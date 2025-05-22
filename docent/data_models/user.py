from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class User(BaseModel):
    """User model for multi-user support in Docent."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    email: str
    created_at: datetime | None = None

    class Config:
        extra = "forbid"


class UserCreateRequest(BaseModel):
    """Request model for creating a new user."""

    email: str

    class Config:
        extra = "forbid"


class UserResponse(BaseModel):
    """Response model for user operations."""

    user_id: str
    email: str

    class Config:
        extra = "forbid"
