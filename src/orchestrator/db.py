from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from orchestrator.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


async def create_schema() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
