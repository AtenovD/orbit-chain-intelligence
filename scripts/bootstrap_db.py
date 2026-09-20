"""Create a local development schema and align Alembic state.

Production deployments should continue to use ``alembic upgrade head``.
"""

import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from orchestrator import models  # noqa: F401
from orchestrator.db import Base, engine


async def bootstrap() -> bool:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        has_version = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).has_table("alembic_version")
        )
        if not has_version:
            return False
        version_count = await connection.scalar(text("SELECT count(*) FROM alembic_version"))
    return bool(version_count)


if __name__ == "__main__":
    version_exists = asyncio.run(bootstrap())
    config = Config("alembic.ini")
    if version_exists:
        command.upgrade(config, "head")
    else:
        command.stamp(config, "head")
