"""
Custom exception classes for the Docent application.
"""


class UserFacingError(Exception):
    """Base exception for errors safe to show to users."""

    status_code: int = 500

    def __init__(self, user_message: str, internal_message: str | None = None):
        self.user_message = user_message
        self.internal_message = internal_message or user_message
        super().__init__(self.internal_message)


class BadRequestError(UserFacingError):
    """Raised for invalid user input or validation failures."""

    status_code: int = 400


class ForbiddenError(UserFacingError):
    """Raised when user lacks permission for an operation."""

    status_code: int = 403


class NotFoundError(UserFacingError):
    """Raised when a requested resource is not found."""

    status_code: int = 404


class ConflictError(UserFacingError):
    """Raised when an operation conflicts with existing state."""

    status_code: int = 409


class DuplicateAgentRunError(ConflictError):
    """Raised when ingesting a duplicate agent run ID."""

    def __init__(self, agent_run_id: str):
        super().__init__(
            user_message=f"An agent run with ID '{agent_run_id}' already exists.",
            internal_message=f"Duplicate agent run ID: {agent_run_id}",
        )
