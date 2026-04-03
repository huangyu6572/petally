"""
Petal Backend — Test Configuration & Shared Fixtures
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import JSON, event
from unittest.mock import AsyncMock

from app.main import create_app
from app.models.models import Base
from app.core.dependencies import get_db, get_redis

# In-memory SQLite for tests (use aiosqlite)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── SQLite 兼容性：JSONB → JSON, BigInteger PK → Integer ─────────────────────
# PostgreSQL 的 JSONB 类型在 SQLite 下不存在；BigInteger 的 autoincrement
# 在 SQLite 下需要用 Integer 才能正确自增
def _patch_types_for_sqlite():
    """Patch JSONB → JSON and BigInteger primary-key → Integer for SQLite."""
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy import BigInteger, Integer as SA_Integer
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, BigInteger) and column.primary_key:
                column.type = SA_Integer()

_patch_types_for_sqlite()


@pytest_asyncio.fixture
async def db_session():
    """Create a fresh database for each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    redis.get.return_value = None
    redis.incr.return_value = 1
    redis.ttl.return_value = 60
    return redis


@pytest_asyncio.fixture
async def client(db_session, mock_redis):
    """Create a test HTTP client with dependency overrides."""
    app = create_app()

    async def override_get_db():
        yield db_session

    async def override_get_redis():
        return mock_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
