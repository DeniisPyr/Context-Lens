import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import URL, create_engine, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from context_lens.dependencies import get_gemini_client
from context_lens.main import create_app
from context_lens.services.answering import Citation, ModelAnswer
from context_lens.settings import DatabaseSettings

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

# Nothing listens on port 1.
UNREACHABLE_SERVER = make_url(
    "postgresql+psycopg://someone:hunter2@127.0.0.1:1/postgres"
)


class FakeGemini:
    def __init__(self) -> None:
        # Passes verification against the default document in test_ask.upload_document.
        self.answer = ModelAnswer(
            status="answered",
            answer="The cat is orange.",
            citations=[Citation(start_line=1, end_line=1, quote="The cat is orange.")],
        )
        self.error: Exception | None = None
        self.prompts: list[str] = []
        self.system_instructions: list[str] = []
        self.response_models: list[type[BaseModel]] = []

    async def ask(
        self, prompt: str, system_instruction: str, response_model: type[BaseModel]
    ) -> ModelAnswer:
        self.prompts.append(prompt)
        self.system_instructions.append(system_instruction)
        self.response_models.append(response_model)
        if self.error is not None:
            raise self.error
        return self.answer


def as_setting(url: URL) -> str:
    # str(url) would hide the password.
    return url.render_as_string(hide_password=False)


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


@contextmanager
def root_logger_restored() -> Iterator[None]:
    # env.py's fileConfig gives the root logger a new handler bound to the current
    # sys.stderr, which later tests must not inherit.
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        yield
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)


def apply_migrations(url: URL, revision: str = "head") -> None:
    with pytest.MonkeyPatch.context() as patch, root_logger_restored():
        patch.setenv("DATABASE_URL", as_setting(url))
        command.upgrade(Config(ALEMBIC_INI), revision)


def drop_connections(url: URL) -> None:
    # Waits, because a connection the server hasn't closed yet would still pass a ping.
    others = "FROM pg_stat_activity WHERE datname = :name AND pid <> pg_backend_pid()"
    admin = create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as connection:
        parameters = {"name": url.database}
        connection.execute(
            text(f"SELECT pg_terminate_backend(pid) {others}"), parameters
        )
        for _ in range(500):
            if not connection.scalar(text(f"SELECT count(*) {others}"), parameters):
                return
            time.sleep(0.01)
    pytest.fail("The server didn't drop the connections.", pytrace=False)


@pytest.fixture(autouse=True)
def no_developer_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Settings reads .env from the working directory and then the environment, and a
    # developer's own values there must not change the results.
    monkeypatch.chdir(tmp_path)
    for name in ("GEMINI_MODEL", "GEMINI_TIMEOUT_SECONDS", "MAX_UPLOAD_BYTES"):
        monkeypatch.delenv(name, raising=False)
    # Replaced rather than removed, because the default is the developer's own database.
    # A test that needs a database asks for one.
    monkeypatch.setenv("DATABASE_URL", as_setting(UNREACHABLE_SERVER))


@pytest.fixture(scope="session")
def postgres_server() -> URL:
    # Session scope runs before no_developer_settings replaces DATABASE_URL, so this is
    # the developer's own server, used only to create throwaway databases on it. .env is
    # named here because tests move the working directory: someone who changed the
    # database's address there expects these tests to find it.
    settings = DatabaseSettings(_env_file=BACKEND_DIR / ".env")
    return make_url(settings.database_url.get_secret_value())


@pytest.fixture
def database(postgres_server: URL, monkeypatch: pytest.MonkeyPatch) -> Iterator[URL]:
    # A database for this test alone, with no tables yet.
    with throwaway_database(postgres_server) as url:
        monkeypatch.setenv("DATABASE_URL", as_setting(url))
        yield url


@pytest.fixture(scope="session")
def shared_database(postgres_server: URL) -> Iterator[URL]:
    with throwaway_database(postgres_server) as url:
        apply_migrations(url)
        yield url


@pytest.fixture
def clean_database(shared_database: URL, monkeypatch: pytest.MonkeyPatch) -> URL:
    # Migrating a database for each test would be slow, so tests share one and only its
    # rows are removed. A test that changes the schema uses `database` instead.
    with create_engine(shared_database, poolclass=NullPool).begin() as connection:
        # A transaction left open by a broken test should fail this, not hang the run.
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("TRUNCATE documents"))
    monkeypatch.setenv("DATABASE_URL", as_setting(shared_database))
    return shared_database


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fake_gemini() -> FakeGemini:
    return FakeGemini()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, fake_gemini: FakeGemini
) -> Iterator[TestClient]:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    app = create_app()
    app.dependency_overrides[get_gemini_client] = lambda: fake_gemini
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client
