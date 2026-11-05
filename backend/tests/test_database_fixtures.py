from uuid import uuid4

import pytest
from conftest import UNREACHABLE_SERVER
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, inspect, make_url, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from context_lens.db.models import DocumentRow
from context_lens.settings import DatabaseSettings


def url_the_app_would_use() -> URL:
    return make_url(DatabaseSettings().database_url.get_secret_value())


def documents_in(url: URL) -> int | None:
    with create_engine(url, poolclass=NullPool).connect() as connection:
        # A developer who hasn't applied the migrations has no such table.
        if connection.scalar(text("SELECT to_regclass('documents')")) is None:
            return None
        return connection.scalar(text("SELECT count(*) FROM documents"))


def test_without_asking_for_a_database_the_url_leads_nowhere() -> None:
    assert url_the_app_would_use() == UNREACHABLE_SERVER


def test_clean_database_is_a_throwaway_and_not_the_developers(
    clean_database: URL, postgres_server: URL
) -> None:
    url = url_the_app_would_use()

    assert url == clean_database
    assert url.database.startswith("context_lens_test_")
    assert url.database != postgres_server.database


def test_database_for_one_test_is_a_throwaway_and_not_the_developers(
    database: URL, postgres_server: URL
) -> None:
    url = url_the_app_would_use()

    assert url == database
    assert url.database.startswith("context_lens_test_")
    assert url.database != postgres_server.database


def test_uploads_reach_the_throwaway_database_and_not_the_developers(
    client: TestClient, clean_database: URL, postgres_server: URL
) -> None:
    before = documents_in(postgres_server)

    response = client.post("/api/documents", files={"file": ("a.txt", b"hello")})

    assert response.status_code == 201
    assert documents_in(clean_database) == 1
    assert documents_in(postgres_server) == before


def test_clean_database_has_the_migrations_applied(clean_database: URL) -> None:
    engine = create_engine(clean_database, poolclass=NullPool)

    assert "documents" in inspect(engine).get_table_names()


def test_database_for_one_test_has_no_tables(database: URL) -> None:
    engine = create_engine(database, poolclass=NullPool)

    assert inspect(engine).get_table_names() == []


@pytest.mark.parametrize("attempt", ["first", "second"])
def test_each_test_starts_without_documents(clean_database: URL, attempt: str) -> None:
    # Whichever runs second would see the row the other one left.
    with Session(create_engine(clean_database, poolclass=NullPool)) as session:
        count = session.scalar(text("SELECT count(*) FROM documents"))
        session.add(
            DocumentRow(id=uuid4(), filename="notes.txt", text="Hello", line_count=1)
        )
        session.commit()

    assert count == 0
