from fastapi import Depends, HTTPException, Request

from docent._db_service.schemas.auth_models import User
from docent._db_service.service import DBService
from docent._server._dependencies.database import get_db


async def require_authenticated_user(request: Request, db: DBService = Depends(get_db)) -> User:
    # Method 1: Check for session-based authentication (from middleware)
    if hasattr(request.state, "user") and request.state.user is not None:
        return request.state.user

    # Method 2: Check for API key authentication
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        api_key = auth_header[7:]  # Remove "Bearer " prefix
        user = await db.get_user_by_email(api_key)
        if user:
            return user

    # No valid authentication found
    raise HTTPException(
        status_code=401, detail="Authentication required. Please log in or provide a valid API key."
    )


async def get_default_view_ctx(fg_id: str, db: DBService = Depends(get_db)):
    return await db.get_default_view_ctx(fg_id)
