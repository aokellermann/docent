"""Database fixtures for integration tests."""

from typing import AsyncGenerator

import pytest_asyncio
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.asyncio.engine import AsyncConnection

from docent_core._db_service.db import DocentDB
from docent_core._db_service.schemas.auth_models import User
from docent_core._db_service.schemas.base import SQLABase
from docent_core._db_service.service import MonoService
from docent_core.services.charts import ChartsService

TEST_DATABASE_URL = URL.create(
    drivername="postgresql+asyncpg",
    username="ubuntu",
    password="your_password_here",
    host="localhost",
    port=5432,
    database="_pytest_docent_test",
)


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(SQLABase.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLABase.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def db_connection(db_engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
    async with db_engine.connect() as connection:
        yield connection
        await connection.close()


@pytest_asyncio.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncGenerator[AsyncSession, None]:
    async with db_connection.begin() as transaction:
        async with AsyncSession(bind=db_connection) as session:
            yield session
            await session.close()
            await transaction.rollback()


@pytest_asyncio.fixture(scope="session")
async def db_service(
    db_engine: AsyncEngine, db_connection: AsyncConnection
) -> AsyncGenerator[DocentDB, None]:
    yield DocentDB(db_engine, async_sessionmaker(bind=db_connection, expire_on_commit=False))


@pytest_asyncio.fixture
async def mono_service(db_service: DocentDB) -> AsyncGenerator[MonoService, None]:
    """
    Test-scoped fixture that provides MonoService with real database.
    """
    service = MonoService(db_service)
    yield service


@pytest_asyncio.fixture
async def charts_service(
    db_session: AsyncSession, mono_service: MonoService
) -> AsyncGenerator[ChartsService, None]:
    """
    Fixture that creates a test charts service and returns it.
    """
    service = ChartsService(db_session, mono_service)
    yield service


@pytest_asyncio.fixture
async def test_collection(mono_service: MonoService, test_user: User) -> AsyncGenerator[str, None]:
    """
    Fixture that creates a test collection and returns its ID.
    Cleans up the collection after the test.
    """
    collection_id = await mono_service.create_collection(
        name="pytest_integration_collection",
        description="Test collection for integration tests",
        user=test_user,
    )
    yield collection_id
    await mono_service.delete_collection(collection_id)


@pytest_asyncio.fixture
async def test_user(mono_service: MonoService) -> AsyncGenerator[User, None]:
    """
    Fixture that creates a test user and returns the user ID.
    """
    user = await mono_service.create_user(
        email="pytest_integration@example.com", password="test_password_123"
    )
    yield user
