import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_init_db_adds_token_count_to_legacy_sqlite_eval_results(
    monkeypatch,
    tmp_path,
):
    import app.database as database
    from app.models import EvalResult

    legacy_engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}",
    )
    async with legacy_engine.begin() as connection:
        await connection.execute(
            text(
                """
                CREATE TABLE eval_results (
                    id VARCHAR PRIMARY KEY,
                    eval_run_id VARCHAR NOT NULL,
                    eval_case_id VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    actual_output TEXT NOT NULL,
                    score FLOAT,
                    error TEXT,
                    latency_ms INTEGER NOT NULL
                )
                """
            )
        )
        await connection.execute(
            text(
                """
                INSERT INTO eval_results (
                    id, eval_run_id, eval_case_id, status,
                    actual_output, score, error, latency_ms
                ) VALUES (
                    'legacy-result', 'legacy-run', 'legacy-case', 'pass',
                    'legacy output', 1.0, NULL, 7
                )
                """
            )
        )

    monkeypatch.setattr(database, "engine", legacy_engine)
    await database.init_db()
    await database.init_db()

    async with legacy_engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"]
                for column in inspect(sync_connection).get_columns("eval_results")
            }
        )
    assert "token_count" in columns

    session_factory = async_sessionmaker(
        legacy_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        legacy = (
            await session.execute(
                select(EvalResult).where(EvalResult.id == "legacy-result")
            )
        ).scalar_one()
        assert legacy.token_count is None

        current = EvalResult(
            eval_run_id="current-run",
            eval_case_id="current-case",
            status="pass",
            actual_output="current output",
            score=1.0,
            latency_ms=8,
            token_count=42,
        )
        session.add(current)
        await session.commit()
        await session.refresh(current)
        assert current.token_count == 42

    await legacy_engine.dispose()
