import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, create_engine, inspect, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from context_lens.services import answering
from context_lens.settings import DatabaseSettings

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

# Nothing listens on port 1.
UNREACHABLE_SERVER = make_url(
    "postgresql+psycopg://someone:hunter2@127.0.0.1:1/postgres"
)


def url_from_settings() -> URL:
    # conftest moved the working directory, so .env is named here: someone who changed
    # the database's address there expects these tests to find it.
    settings = DatabaseSettings(_env_file=BACKEND_DIR / ".env")
    return make_url(settings.database_url.get_secret_value())


@contextmanager
def throwaway_database(server: URL) -> Iterator[URL]:
    name = f"context_lens_test_{uuid4().hex}"
    # CREATE DATABASE and DROP DATABASE refuse to run inside a transaction.
    admin = create_engine(
        server.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError as error:
        # Only the first line: psycopg adds one more for each address it tried.
        reason = str(error.orig).splitlines()[0]
        message = (
            "Can't reach Postgres. Run `docker compose up -d --wait` from the repo "
            f"root. ({reason})"
        )
        if os.environ.get("CI"):
            pytest.fail(message, pytrace=False)
        pytest.skip(message)
    try:
        yield server.set(database=name)
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))


def tables_in(url: URL) -> set[str]:
    engine = create_engine(url, poolclass=NullPool)
    return set(inspect(engine).get_table_names())


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    # env.py's fileConfig gives the root logger a new handler bound to this test's
    # sys.stderr, which later tests must not inherit.
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[URL]:
    with throwaway_database(url_from_settings()) as url:
        # str(url) would hide the password.
        monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
        yield url


@pytest.fixture
def alembic_config(database: URL) -> Config:
    return Config(ALEMBIC_INI)


@pytest.fixture
def migrated(alembic_config: Config) -> Config:
    command.upgrade(alembic_config, "head")
    return alembic_config


def outcome_of_unreachable_server() -> BaseException:
    # Catches both, because a skip that escaped would skip the test, not fail it.
    with (
        pytest.raises((pytest.skip.Exception, pytest.fail.Exception)) as outcome,
        throwaway_database(UNREACHABLE_SERVER),
    ):
        pass
    return outcome.value


def test_unreachable_server_skips_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)

    outcome = outcome_of_unreachable_server()

    assert isinstance(outcome, pytest.skip.Exception)
    assert "docker compose up -d --wait" in str(outcome)


def test_unreachable_server_fails_on_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")

    outcome = outcome_of_unreachable_server()

    assert isinstance(outcome, pytest.fail.Exception)
    assert "docker compose up -d --wait" in str(outcome)


def test_unreachable_server_message_hides_the_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI", raising=False)

    outcome = outcome_of_unreachable_server()

    assert "hunter2" not in str(outcome)


def test_throwaway_database_is_separate_and_dropped_afterwards() -> None:
    server = url_from_settings()
    admin = create_engine(server.set(database="postgres"), poolclass=NullPool)

    def exists(name: str | None) -> bool:
        with admin.connect() as connection:
            query = text("SELECT count(*) FROM pg_database WHERE datname = :name")
            return connection.scalar(query, {"name": name}) == 1

    with throwaway_database(server) as url:
        assert url.database != server.database
        assert url.database.startswith("context_lens_test_")
        assert exists(url.database)
        # Still connected when the database is dropped, as a failed test can leave it.
        leftover = create_engine(url, poolclass=NullPool).connect()

    leftover.invalidate()
    assert not exists(url.database)


def test_alembic_ini_holds_no_database_url() -> None:
    assert Config(ALEMBIC_INI).get_main_option("sqlalchemy.url") is None


def test_migrations_use_the_database_url_from_settings(
    migrated: Config, database: URL
) -> None:
    assert "alembic_version" in tables_in(database)


def test_percent_sign_in_the_url_works(
    alembic_config: Config, database: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    # URL-encoded passwords contain %, but creating a role for one is not worth it.
    with_percent = database.update_query_dict({"application_name": "100%"})
    monkeypatch.setenv(
        "DATABASE_URL", with_percent.render_as_string(hide_password=False)
    )

    command.upgrade(alembic_config, "head")

    assert "alembic_version" in tables_in(database)


def test_migrations_never_print_the_url(
    alembic_config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    command.upgrade(alembic_config, "head")

    output = capsys.readouterr()
    assert "Context impl" in output.err  # Proves the output is being captured at all.
    assert "://" not in output.out + output.err


def test_logging_still_works_after_a_migration(
    migrated: Config, caplog: pytest.LogCaptureFixture
) -> None:
    # The migration ran during setup, so this test is in the position of any later
    # one: caplog is attached again and the app's loggers existed before fileConfig.
    answering.logger.warning("still logging")

    assert "still logging" in caplog.text
