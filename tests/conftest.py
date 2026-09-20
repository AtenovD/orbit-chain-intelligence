import os
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

TEST_DB = Path(__file__).parent / "test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB.as_posix()}"

from orchestrator.db import Base, engine  # noqa: E402
from orchestrator.config import get_settings  # noqa: E402
from orchestrator.main import app  # noqa: E402
from orchestrator.runtime import runtime  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def database():
    settings = get_settings()
    original_auth = settings.auth_required
    original_verification = settings.email_verification_required
    settings.auth_required = False
    settings.email_verification_required = False
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    await runtime.shutdown()
    # Cancelled workers may have checked out a SQLite connection while their
    # transaction was being rolled back. Dispose the test pool before DDL so a
    # stale file lock cannot leak into the next function-scoped database.
    await engine.dispose()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    settings.auth_required = original_auth
    settings.email_verification_required = original_verification


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value
