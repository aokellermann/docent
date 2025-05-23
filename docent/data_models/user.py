from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    """Core user model representing a user in the system."""

    id: str
    email: str
    created_at: datetime | None = None
