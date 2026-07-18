from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    from app.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_sqlite_eval_result_usage(conn)


async def _migrate_sqlite_eval_result_usage(connection: AsyncConnection) -> None:
    """Add usage persistence to databases created before token tracking."""
    if connection.dialect.name != "sqlite":
        return

    columns = (
        await connection.execute(text("PRAGMA table_info(eval_results)"))
    ).mappings()
    if "token_count" not in {str(column["name"]) for column in columns}:
        await connection.execute(
            text("ALTER TABLE eval_results ADD COLUMN token_count INTEGER")
        )
