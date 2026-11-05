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
    create_dataset,
    drop_connections,
    run_sql,
)
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import IntegrityError, InterfaceError, ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from context_lens.db.dataset_store import DatasetRejectedError, DatasetStore
from context_lens.db.document_store import DocumentRejectedError, DocumentStore

UNAVAILABLE = {"detail": "The database is unavailable right now. Please try again."}
NOT_READY = {
    "detail": (
        "The database isn't ready. Apply its migrations with: "
        "uv run alembic upgrade head"
    )
}

NO_SUCH_ID = "00000000-0000-0000-0000-000000000000"
NO_SUCH_DATASET_DOCUMENTS = f"/api/datasets/{NO_SUCH_ID}/documents"
PRIVATE_TEXT = "private document text"
UPLOAD = {"files": {"file": ("notes.txt", PRIVATE_TEXT.encode())}}

EVERY_ROUTE = [
    pytest.param("GET", "/api/datasets", {}, id="list_datasets"),
    pytest.param("POST", "/api/datasets", {"json": {"name": "A"}}, id="create_dataset"),
    pytest.param("GET", NO_SUCH_DATASET_DOCUMENTS, {}, id="list_documents"),
    pytest.param("POST", NO_SUCH_DATASET_DOCUMENTS, UPLOAD, id="upload"),
    pytest.param("GET", f"/api/documents/{NO_SUCH_ID}", {}, id="read"),
    pytest.param(
        "POST",
        "/api/ask",
        {"json": {"document_id": NO_SUCH_ID, "question": "Hi"}},
        id="ask",
    ),
    pytest.param("DELETE", f"/api/documents/{NO_SUCH_ID}", {}, id="delete_document"),
    pytest.param("DELETE", f"/api/datasets/{NO_SUCH_ID}", {}, id="delete_dataset"),
]
# Deleting a document needs only its id column, which 0001 already has, so that route
# works before the later migrations and answers 404 for an unknown id.
ROUTES_THAT_NEED_THE_LATER_MIGRATIONS = [
    route for route in EVERY_ROUTE if route.id != "delete_document"
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
    client_without_database.post(NO_SUCH_DATASET_DOCUMENTS, **UPLOAD)

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


@pytest.mark.parametrize(
    ("method", "path", "request_parts", "detail"),
    [
        ("GET", "/api/documents/not-a-uuid", {}, "Document not found."),
        ("GET", "/api/datasets/not-a-uuid/documents", {}, "Dataset not found."),
        ("POST", "/api/datasets/not-a-uuid/documents", UPLOAD, "Dataset not found."),
        ("DELETE", "/api/documents/not-a-uuid", {}, "Document not found."),
        ("DELETE", "/api/datasets/not-a-uuid", {}, "Dataset not found."),
    ],
    ids=["read", "list_documents", "upload", "delete_document", "delete_dataset"],
)
def test_bad_id_is_a_404_even_with_the_database_down(
    client_without_database: TestClient,
    method: str,
    path: str,
    request_parts: dict,
    detail: str,
) -> None:
    response = client_without_database.request(method, path, **request_parts)

    assert response.status_code == 404
    assert response.json() == {"detail": detail}


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


@pytest.mark.parametrize("revision", ["0001", "0002"])
@pytest.mark.parametrize(
    ("method", "path", "request_parts"), ROUTES_THAT_NEED_THE_LATER_MIGRATIONS
)
def test_missing_column_or_table_asks_for_the_migrations(
    database: URL,
    start_app: StartApp,
    revision: str,
    method: str,
    path: str,
    request_parts: dict,
) -> None:
    # Someone who applied an earlier migration before this code existed.
    apply_migrations(database, revision)

    with start_app() as client:
        response = client.request(method, path, **request_parts)

    assert response.status_code == 503
    assert response.json() == NOT_READY


def test_documents_without_their_dataset_column_ask_for_the_migrations(
    database: URL, start_app: StartApp
) -> None:
    # The datasets table is already there at this revision, so only these routes fail.
    apply_migrations(database, "0003")

    with start_app() as client:
        documents_url = create_dataset(client)
        responses = [
            client.get(documents_url),
            client.post(documents_url, **UPLOAD),
            client.get(f"/api/documents/{NO_SUCH_ID}"),
            client.post("/api/ask", json={"document_id": NO_SUCH_ID, "question": "Hi"}),
        ]

    assert [response.status_code for response in responses] == [503] * 4
    assert all(response.json() == NOT_READY for response in responses)


def test_missing_migrations_are_logged_without_the_text(
    database: URL, start_app: StartApp, caplog: pytest.LogCaptureFixture
) -> None:
    with start_app() as client:
        client.post(NO_SUCH_DATASET_DOCUMENTS, **UPLOAD)

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
        documents_url = create_dataset(client)
        # Nothing handles this one, so the server logs the exception as it is.
        with pytest.raises(DocumentRejectedError, match="violates") as error:
            client.post(documents_url, **UPLOAD)
        assert client.get(documents_url).json() == []

    assert PRIVATE_TEXT not in "".join(format_exception(error.value))
    assert PRIVATE_TEXT not in caplog.text


def refuse_deleting_documents(database: URL) -> None:
    # Another table that points at documents without ON DELETE CASCADE, as a later one
    # could by mistake, and a row in it for every document.
    run_sql(
        database,
        "CREATE TABLE pins (document_id uuid NOT NULL REFERENCES documents (id))",
    )
    run_sql(database, "INSERT INTO pins SELECT id FROM documents")


@pytest.mark.parametrize("target", ["document", "dataset"])
def test_refused_delete_keeps_everything_and_is_logged_without_the_text(
    database: URL, start_app: StartApp, caplog: pytest.LogCaptureFixture, target: str
) -> None:
    apply_migrations(database)

    with start_app() as client:
        documents_url = create_dataset(client)
        uploaded = client.post(documents_url, **UPLOAD).json()
        refuse_deleting_documents(database)
        path = {
            "document": f"/api/documents/{uploaded['id']}",
            "dataset": documents_url.removesuffix("/documents"),
        }[target]
        # Nothing handles this one, so the server logs the exception as it is.
        with pytest.raises(IntegrityError, match="still referenced") as error:
            client.delete(path)
        # One transaction: a dataset whose documents can't go stays as well.
        assert client.get(documents_url).json() == [uploaded]
        assert client.get(f"/api/documents/{uploaded['id']}").status_code == 200

    assert PRIVATE_TEXT not in "".join(format_exception(error.value))
    assert PRIVATE_TEXT not in caplog.text


def test_duplicate_file_is_answered_without_the_text_anywhere(
    client: TestClient, documents_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    client.post(documents_url, **UPLOAD)

    response = client.post(documents_url, **UPLOAD)

    assert response.status_code == 409
    assert response.json() == {"detail": "notes.txt is already in this dataset."}
    assert PRIVATE_TEXT not in caplog.text


def test_unknown_dataset_is_answered_without_the_text_anywhere(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    response = client.post(NO_SUCH_DATASET_DOCUMENTS, **UPLOAD)

    assert response.status_code == 404
    assert response.json() == {"detail": "Dataset not found."}
    assert PRIVATE_TEXT not in caplog.text


def test_refused_dataset_is_logged_without_the_name(
    database: URL, start_app: StartApp, caplog: pytest.LogCaptureFixture
) -> None:
    apply_migrations(database)
    run_sql(database, "ALTER TABLE datasets ADD CONSTRAINT refuse_all CHECK (false)")

    with start_app() as client:
        with pytest.raises(DatasetRejectedError, match="violates") as error:
            client.post("/api/datasets", json={"name": PRIVATE_TEXT})
        assert client.get("/api/datasets").json() == []

    assert PRIVATE_TEXT not in "".join(format_exception(error.value))
    assert PRIVATE_TEXT not in caplog.text


def test_duplicate_dataset_name_is_answered_without_logging_the_name(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    client.post("/api/datasets", json={"name": PRIVATE_TEXT})

    response = client.post("/api/datasets", json={"name": PRIVATE_TEXT})

    assert response.status_code == 409
    assert PRIVATE_TEXT not in response.text
    assert PRIVATE_TEXT not in caplog.text


def test_unreachable_server_while_creating_a_dataset_is_logged_without_the_name(
    client_without_database: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    client_without_database.post("/api/datasets", json={"name": PRIVATE_TEXT})

    assert "Connection refused" in unavailable_log(caplog).getMessage()
    assert PRIVATE_TEXT not in caplog.text


@pytest.mark.parametrize(
    ("store_type", "attribute", "path"),
    [
        (DocumentStore, "document_store", NO_SUCH_DATASET_DOCUMENTS),
        (DatasetStore, "dataset_store", "/api/datasets"),
    ],
    ids=["documents", "datasets"],
)
def test_busy_connection_pool_is_a_503(
    client: TestClient,
    clean_database: URL,
    caplog: pytest.LogCaptureFixture,
    store_type: type,
    attribute: str,
    path: str,
) -> None:
    # A real pool with room for one connection, which this test keeps busy.
    engine = create_async_engine(
        as_setting(clean_database), pool_size=1, max_overflow=0, pool_timeout=0.1
    )
    setattr(client.app.state, attribute, store_type(engine))
    busy = client.portal.call(engine.connect)
    try:
        response = client.get(path)
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

    client_without_database.app.state.dataset_store = BrokenStore()

    response = client_without_database.get("/api/datasets")

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
    client: TestClient,
    documents_url: str,
    clean_database: URL,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The lock keeps the upload waiting inside its INSERT until its connection is gone.
    engine = create_engine(clean_database, poolclass=NullPool)
    with ThreadPoolExecutor() as executor, engine.connect() as locker:
        locker.execute(text("LOCK TABLE documents"))
        upload = executor.submit(client.post, documents_url, **UPLOAD)

        drop_the_blocked_connection(clean_database)

        response = upload.result(timeout=10)

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE
    assert "terminating connection" in unavailable_log(caplog).getMessage()
    assert PRIVATE_TEXT not in caplog.text


def test_app_recovers_by_itself_once_the_server_is_back(
    client: TestClient, documents_url: str, clean_database: URL
) -> None:
    uploaded = client.post(documents_url, **UPLOAD).json()
    assert client.app.state.engine.pool.checkedin() == 1

    # What the pool sees after a restart: every connection it kept is dead.
    drop_connections(clean_database)

    assert client.get(documents_url).json() == [uploaded]
