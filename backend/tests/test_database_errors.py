import logging
from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep
from traceback import format_exception

import pytest
from conftest import (
    FakeGemini,
    StartApp,
    apply_migrations,
    as_setting,
    drop_connections,
    run_sql,
)
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import InterfaceError, ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from context_lens.db.document_store import DocumentRejectedError, DocumentStore

UNAVAILABLE = {"detail": "The database is unavailable right now. Please try again."}
NOT_READY = {
    "detail": (
        "The database isn't ready. Apply its migrations with: "
        "uv run alembic upgrade head"
    )
}

NO_SUCH_DOCUMENT = "00000000-0000-0000-0000-000000000000"
PRIVATE_TEXT = "private document text"
UPLOAD = {"files": {"file": ("notes.txt", PRIVATE_TEXT.encode())}}

EVERY_ROUTE = [
    pytest.param("GET", "/api/documents", {}, id="list"),
    pytest.param("POST", "/api/documents", UPLOAD, id="upload"),
    pytest.param("GET", f"/api/documents/{NO_SUCH_DOCUMENT}", {}, id="read"),
    pytest.param(
        "POST",
        "/api/ask",
        {"json": {"document_id": NO_SUCH_DOCUMENT, "question": "Hi"}},
        id="ask",
    ),
]


def logged_errors(
    caplog: pytest.LogCaptureFixture, message: str
) -> list[BaseException]:
    records = [r for r in caplog.records if r.getMessage() == message]
    return [record.exc_info[1] for record in records if record.exc_info]


def unavailable_log(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    prefix = "The database is unavailable: "
    [record] = [r for r in caplog.records if r.getMessage().startswith(prefix)]
    return record


@pytest.mark.parametrize(("method", "path", "request_parts"), EVERY_ROUTE)
def test_unreachable_server_is_a_503(
    client_without_database: TestClient,
    fake_gemini: FakeGemini,
    method: str,
    path: str,
    request_parts: dict,
) -> None:
    response = client_without_database.request(method, path, **request_parts)

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE
    assert fake_gemini.prompts == []


def test_unreachable_server_is_logged_in_one_line_without_the_text_or_password(
    client_without_database: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    client_without_database.post("/api/documents", **UPLOAD)

    record = unavailable_log(caplog)
    assert record.exc_info is None
    assert "\n" not in record.getMessage()
    assert "Connection refused" in record.getMessage()
    assert PRIVATE_TEXT not in caplog.text
    assert "hunter2" not in caplog.text


def test_postgres_keeps_refused_rows_out_of_its_own_log(database: URL) -> None:
    with create_engine(database, poolclass=NullPool).connect() as connection:
        verbosity = connection.execute(text("SHOW log_error_verbosity")).scalar()

    assert verbosity == "terse"


def test_bad_id_is_a_404_even_with_the_database_down(
    client_without_database: TestClient,
) -> None:
    response = client_without_database.get("/api/documents/not-a-uuid")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


@pytest.mark.parametrize(("method", "path", "request_parts"), EVERY_ROUTE)
def test_missing_table_asks_for_the_migrations(
    database: URL,
    start_app: StartApp,
    fake_gemini: FakeGemini,
    method: str,
    path: str,
    request_parts: dict,
) -> None:
    with start_app() as client:
        response = client.request(method, path, **request_parts)

    assert response.status_code == 503
    assert response.json() == NOT_READY
    assert fake_gemini.prompts == []


@pytest.mark.parametrize(("method", "path", "request_parts"), EVERY_ROUTE)
def test_missing_column_asks_for_the_migrations(
    database: URL, start_app: StartApp, method: str, path: str, request_parts: dict
) -> None:
    # Someone who applied 0001 before this code existed, and hasn't applied 0002.
    apply_migrations(database, "0001")

    with start_app() as client:
        response = client.request(method, path, **request_parts)

    assert response.status_code == 503
    assert response.json() == NOT_READY


def test_missing_migrations_are_logged_without_the_text(
    database: URL, start_app: StartApp, caplog: pytest.LogCaptureFixture
) -> None:
    with start_app() as client:
        client.post("/api/documents", **UPLOAD)

    [error] = logged_errors(caplog, "The database isn't ready.")
    assert isinstance(error, ProgrammingError)
    assert "INSERT INTO documents" in caplog.text  # The traceback is in there.
    assert PRIVATE_TEXT not in caplog.text


def test_refused_write_is_logged_without_the_text(
    database: URL, start_app: StartApp, caplog: pytest.LogCaptureFixture
) -> None:
    apply_migrations(database)
    run_sql(database, "ALTER TABLE documents ADD CONSTRAINT refuse_all CHECK (false)")

    with start_app() as client:
        # Nothing handles this one, so the server logs the exception as it is.
        with pytest.raises(DocumentRejectedError, match="violates") as error:
            client.post("/api/documents", **UPLOAD)
        assert client.get("/api/documents").json() == []

    assert PRIVATE_TEXT not in "".join(format_exception(error.value))
    assert PRIVATE_TEXT not in caplog.text


def test_busy_connection_pool_is_a_503(
    client: TestClient, clean_database: URL, caplog: pytest.LogCaptureFixture
) -> None:
    # A real pool with room for one connection, which this test keeps busy.
    engine = create_async_engine(
        as_setting(clean_database), pool_size=1, max_overflow=0, pool_timeout=0.1
    )
    client.app.state.document_store = DocumentStore(engine)
    busy = client.portal.call(engine.connect)
    try:
        response = client.get("/api/documents")
    finally:
        client.portal.call(busy.close)
        client.portal.call(engine.dispose)

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE
    assert "QueuePool limit" in unavailable_log(caplog).getMessage()


def test_interface_error_is_a_503(client_without_database: TestClient) -> None:
    # Stopping the server never caused one for real, so a store raises it here.
    class BrokenStore:
        async def list_all(self) -> None:
            raise InterfaceError("SELECT 1", {}, Exception("the connection is closed"))

    client_without_database.app.state.document_store = BrokenStore()

    response = client_without_database.get("/api/documents")

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE


def drop_the_blocked_connection(url: URL) -> None:
    drop = (
        "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity "
        "WHERE datname = :name AND wait_event_type = 'Lock'"
    )
    admin = create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    deadline = monotonic() + 10
    with admin.connect() as connection:
        while not connection.scalar(text(drop), {"name": url.database}):
            assert monotonic() < deadline, "The upload never reached the database."
            sleep(0.01)


def test_connection_lost_during_a_write_is_a_503(
    client: TestClient, clean_database: URL, caplog: pytest.LogCaptureFixture
) -> None:
    # The lock keeps the upload waiting inside its INSERT until its connection is gone.
    engine = create_engine(clean_database, poolclass=NullPool)
    with ThreadPoolExecutor() as executor, engine.connect() as locker:
        locker.execute(text("LOCK TABLE documents"))
        upload = executor.submit(client.post, "/api/documents", **UPLOAD)

        drop_the_blocked_connection(clean_database)

        response = upload.result(timeout=10)

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE
    assert "terminating connection" in unavailable_log(caplog).getMessage()
    assert PRIVATE_TEXT not in caplog.text


def test_app_recovers_by_itself_once_the_server_is_back(
    client: TestClient, clean_database: URL
) -> None:
    uploaded = client.post("/api/documents", **UPLOAD).json()
    assert client.app.state.engine.pool.checkedin() == 1

    # What the pool sees after a restart: every connection it kept is dead.
    drop_connections(clean_database)

    assert client.get("/api/documents").json() == [uploaded]
