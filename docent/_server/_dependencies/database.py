"""
Database dependency for FastAPI endpoints.

This module provides the get_db dependency that can be imported and used
across different modules without circular imports.
"""

from docent._db_service.service import DBService

_db = None


async def get_db():
    """FastAPI dependency to get the database service instance."""
    global _db
    if _db is None:
        _db = await DBService.init()
    return _db


async def get_default_view_ctx(fg_id: str):
    """FastAPI dependency to get the default view context for a framegrid."""
    db = await get_db()
    return await db.get_default_view_ctx(fg_id)
