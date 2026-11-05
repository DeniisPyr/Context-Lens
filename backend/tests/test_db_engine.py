from collections.abc import AsyncIterator

import pytest
from conftest import UNREACHABLE_SERVER, as_setting, drop_connections
from sqlalchemy import URL, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from context_lens.db.engine import create_database_engine
from context_lens.settings import DatabaseSettings

pytestmark = pytest.mark.anyio


@pytest.fixture
def unreachable_engine() -> AsyncEngine:
    return create_database_engine(DatabaseSettings(_env_file=None))


@pytest.fixture
async def engine(clean_database: URL) -> AsyncIterator[AsyncEngine]:
    engine = create_database_engine(DatabaseSettings(_env_file=None))
    yield engine
    await engine.dispose()


def test_engine_uses_the_url_from_settings_with_its_password(
    unreachable_engine: AsyncEngine,
) -> None:
    url = unreachable_engine.url.render_as_string(hide_password=False)

    assert url == as_setting(UNREACHABLE_SERVER)


def test_creating_the_engine_does_not_connect(unreachable_engine: AsyncEngine) -> None:
    assert unreachable_engine.pool.checkedout() == 0
    assert unreachable_engine.pool.checkedin() == 0


async def test_connecting_goes_through_the_async_driver(
    unreachable_engine: AsyncEngine,
) -> None:
    # Without the sqlalchemy[asyncio] extra this fails on the missing greenlet instead.
    with pytest.raises(OperationalError) as error:
        async with unreachable_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    assert "hunter2" not in str(error.value)


async def test_engine_runs_queries(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT 1")) == 1


async def test_engine_replaces_a_connection_the_server_dropped(
    engine: AsyncEngine, clean_database: URL
) -> None:
    backend = text("SELECT pg_backend_pid()")
    async with engine.connect() as connection:
        first = await connection.scalar(backend)
    assert engine.pool.checkedin() == 1

    drop_connections(clean_database)

    async with engine.connect() as connection:
        assert await connection.scalar(backend) != first


async def test_error_message_hides_the_statement_parameters(
    engine: AsyncEngine,
) -> None:
    statement = text("INSERT INTO no_such_table (body) VALUES (:body)")

    with pytest.raises(ProgrammingError) as error:
        async with engine.begin() as connection:
            await connection.execute(statement, {"body": "PRIVATE TEXT"})

    assert "no_such_table" in str(error.value)
    assert "PRIVATE TEXT" not in str(error.value)
