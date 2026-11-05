import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from context_lens.db.engine import create_database_engine
from context_lens.settings import DatabaseSettings

pytestmark = pytest.mark.anyio

# Nothing listens on port 1.
UNREACHABLE_URL = "postgresql+psycopg://someone:hunter2@127.0.0.1:1/postgres"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> DatabaseSettings:
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_URL)
    return DatabaseSettings(_env_file=None)


def test_engine_uses_the_url_from_settings_with_its_password(
    settings: DatabaseSettings,
) -> None:
    engine = create_database_engine(settings)

    assert engine.url.render_as_string(hide_password=False) == UNREACHABLE_URL


def test_engine_hides_statement_parameters(settings: DatabaseSettings) -> None:
    assert create_database_engine(settings).sync_engine.hide_parameters is True


def test_creating_the_engine_does_not_connect(settings: DatabaseSettings) -> None:
    engine = create_database_engine(settings)

    assert engine.pool.checkedout() == 0
    assert engine.pool.checkedin() == 0


async def test_connecting_goes_through_the_async_driver(
    settings: DatabaseSettings,
) -> None:
    # Without the sqlalchemy[asyncio] extra this fails on the missing greenlet instead.
    engine = create_database_engine(settings)

    with pytest.raises(OperationalError) as error:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    assert "hunter2" not in str(error.value)
