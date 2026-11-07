import asyncio
import hashlib
import json
import logging
import os
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from uuid import UUID, uuid4

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
from context_lens.services.embeddings import EMBEDDING_DIMENSIONS
from context_lens.services.indexing import EmbeddedChunk
from context_lens.settings import DatabaseSettings

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

# Nothing listens on port 1.
UNREACHABLE_SERVER = make_url(
    "postgresql+psycopg://someone:hunter2@127.0.0.1:1/postgres"
)

type StartApp = Callable[[], AbstractContextManager[TestClient]]

# For tests about documents, where their chunks and the limit on them don't matter.
NO_CHUNKS: list[EmbeddedChunk] = []
MAX_DOCUMENTS = 100


def fake_embedding(text: str) -> list[float]:
    # The same for the same text and different for another, so a test can tell which
    # text a stored embedding is for. Multiples of 1/256 survive Postgres's 32-bit
    # floats exactly.
    digest = hashlib.sha256(text.encode()).digest()
    return [digest[index % len(digest)] / 256 for index in range(EMBEDDING_DIMENSIONS)]


class FakeGemini:
    def __init__(self) -> None:
        # Passes verification against the default document in test_ask.upload_document.
        self.answer = ModelAnswer(
            status="answered",
            answer="The cat is orange.",
            citations=[
                Citation(
                    file="notes.txt",
                    start_line=1,
                    end_line=1,
                    quote="The cat is orange.",
                )
            ],
        )
        self.error: Exception | None = None
        self.during_call: Callable[[], None] = lambda: None
        self.prompts: list[str] = []
        self.system_instructions: list[str] = []
        self.response_models: list[type[BaseModel]] = []
        self.embed_error: Exception | None = None
        self.during_embed: Callable[[list[str]], None] = lambda texts: None
        # The texts of each call to embed.
        self.embedded: list[list[str]] = []
        self.closed = False

    async def ask(
        self, prompt: str, system_instruction: str, response_model: type[BaseModel]
    ) -> ModelAnswer:
        self.prompts.append(prompt)
        self.system_instructions.append(system_instruction)
        self.response_models.append(response_model)
        self.during_call()
        if self.error is not None:
            raise self.error
        return self.answer

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.embedded.append(texts)
        self.during_embed(texts)
        if self.embed_error is not None:
            raise self.embed_error
        return [fake_embedding(text) for text in texts]

    async def aclose(self) -> None:
        self.closed = True


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


def run_sql(url: URL, statement: str) -> None:
    with create_engine(url, poolclass=NullPool).begin() as connection:
        connection.execute(text(statement))


async def wait_for_a_blocked_query(url: URL) -> None:
    # Gives the query being waited for the event loop while this polls for it.
    query = text(
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE datname = :name AND wait_event_type = 'Lock'"
    )
    admin = create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as connection:
        for _ in range(500):
            if connection.scalar(query, {"name": url.database}):
                return
            await asyncio.sleep(0.01)
    pytest.fail("Nothing ever waited for the lock.", pytrace=False)


def create_dataset(client: TestClient, name: str = "Reports") -> str:
    """Creates a dataset and returns the address of its documents."""
    response = client.post("/api/datasets", json={"name": name})
    assert response.status_code == 201
    return f"/api/datasets/{response.json()['id']}/documents"


def stored_chunks(url: URL, document_id: str) -> list[EmbeddedChunk]:
    query = text(
        "SELECT start_line, end_line, text, embedding::text AS embedding "
        "FROM chunks WHERE document_id = :id ORDER BY position"
    )
    with create_engine(url, poolclass=NullPool).connect() as connection:
        rows = connection.execute(query, {"id": UUID(document_id)})
        # pgvector writes a vector as a JSON array.
        return [
            EmbeddedChunk(
                row.start_line, row.end_line, row.text, json.loads(row.embedding)
            )
            for row in rows
        ]


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
    for name in (
        "GEMINI_MODEL",
        "GEMINI_EMBEDDING_MODEL",
        "GEMINI_TIMEOUT_SECONDS",
        "MAX_UPLOAD_BYTES",
        "MAX_DOCUMENTS_PER_DATASET",
    ):
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
        connection.execute(text("TRUNCATE chunks, documents, datasets"))
    monkeypatch.setenv("DATABASE_URL", as_setting(shared_database))
    return shared_database


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fake_gemini() -> FakeGemini:
    return FakeGemini()


@pytest.fixture
def start_app(monkeypatch: pytest.MonkeyPatch, fake_gemini: FakeGemini) -> StartApp:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    @contextmanager
    def start() -> Iterator[TestClient]:
        app = create_app()
        app.dependency_overrides[get_gemini_client] = lambda: fake_gemini
        # As a context manager, so that the lifespan and the requests share the one
        # event loop that the engine's connections belong to.
        with TestClient(app, follow_redirects=False) as test_client:
            yield test_client

    return start


@pytest.fixture
def client(clean_database: URL, start_app: StartApp) -> Iterator[TestClient]:
    with start_app() as test_client:
        yield test_client


@pytest.fixture
def client_without_database(start_app: StartApp) -> Iterator[TestClient]:
    with start_app() as test_client:
        yield test_client


@pytest.fixture
def documents_url(client: TestClient) -> str:
    return create_dataset(client)
