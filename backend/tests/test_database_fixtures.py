from uuid import uuid4

import pytest
from conftest import UNREACHABLE_SERVER
from sqlalchemy import URL, create_engine, inspect, make_url, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from context_lens.db.models import DocumentRow
from context_lens.settings import DatabaseSettings


def url_the_app_would_use() -> URL:
    return make_url(DatabaseSettings().database_url.get_secret_value())


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
        session.add(DocumentRow(id=uuid4(), filename="notes.txt", text="Hello"))
        session.commit()

    assert count == 0
