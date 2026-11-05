from concurrent.futures import ThreadPoolExecutor
from unittest.mock import ANY
from uuid import UUID

import pytest
from conftest import StartApp, run_sql
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import URL as DatabaseURL

URL = "/api/datasets"
TAKEN = {"detail": "A dataset with this name already exists."}


def create(client: TestClient, name: str = "Reports") -> Response:
    return client.post(URL, json={"name": name})


def test_create_returns_the_dataset(client: TestClient) -> None:
    response = create(client, "Výroční zprávy")

    assert response.status_code == 201
    assert response.json() == {"id": ANY, "name": "Výroční zprávy"}
    UUID(response.json()["id"])


def test_created_dataset_is_in_the_list(client: TestClient) -> None:
    created = create(client).json()

    assert client.get(URL).json() == [created]


@pytest.mark.parametrize(
    "name",
    [
        "x" * 100,
        "ž" * 100,
        "a",
        "<b>tučně</b> & 'víc'",
        "50% %(id)s :name $1 ;--",
        "two  spaces inside",
    ],
)
def test_name_comes_back_exactly_as_it_was_sent(client: TestClient, name: str) -> None:
    response = create(client, name)

    assert response.status_code == 201
    assert response.json()["name"] == name
    assert client.get(URL).json() == [response.json()]


@pytest.mark.parametrize(
    ("sent", "stored"),
    [
        ("  Reports  ", "Reports"),
        ("\t\nReports\r\n", "Reports"),
        ("   " + "x" * 100 + "   ", "x" * 100),
    ],
)
def test_name_is_stripped_before_it_is_checked_and_stored(
    client: TestClient, sent: str, stored: str
) -> None:
    response = create(client, sent)

    assert response.status_code == 201
    assert response.json()["name"] == stored
    assert client.get(URL).json() == [response.json()]


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="spaces"),
        pytest.param(" \t\r\n ", id="whitespace"),
        pytest.param("x" * 101, id="101_characters"),
        pytest.param("ž" * 101, id="101_czech_characters"),
        pytest.param("\x00", id="only_nul"),
        pytest.param("a\x00b", id="nul_inside"),
        pytest.param(" a\x00 ", id="nul_with_spaces"),
    ],
)
def test_invalid_name_is_a_validation_error_and_stores_nothing(
    client: TestClient, name: str
) -> None:
    response = create(client, name)

    assert response.status_code == 422
    assert client.get(URL).json() == []


@pytest.mark.parametrize(
    "body", [{}, {"name": None}, {"name": 5}, {"name": ["a"]}, {"title": "Reports"}]
)
def test_body_without_a_text_name_is_a_validation_error(
    client: TestClient, body: dict
) -> None:
    response = client.post(URL, json=body)

    assert response.status_code == 422
    assert client.get(URL).json() == []


def test_duplicate_name_is_a_conflict(client: TestClient) -> None:
    first = create(client).json()

    response = create(client)

    assert response.status_code == 409
    assert response.json() == TAKEN
    assert client.get(URL).json() == [first]


def test_name_is_compared_after_stripping(client: TestClient) -> None:
    create(client, "Reports")

    response = create(client, "  Reports ")

    assert response.status_code == 409


def test_names_differing_only_in_case_are_different_names(client: TestClient) -> None:
    create(client, "Reports")

    assert create(client, "reports").status_code == 201


def test_a_failed_create_does_not_stop_the_next_one(client: TestClient) -> None:
    first = create(client, "Reports").json()
    create(client, "Reports")

    second = create(client, "Invoices")

    assert second.status_code == 201
    assert client.get(URL).json() == [first, second.json()]


def test_only_one_of_many_requests_racing_for_a_name_wins(
    client: TestClient,
) -> None:
    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(lambda _: create(client), range(8)))

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [201] + [409] * 7
    assert len(client.get(URL).json()) == 1
    assert all(r.json() == TAKEN for r in responses if r.status_code == 409)


def test_list_is_empty_without_datasets(client: TestClient) -> None:
    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == []


def test_list_holds_only_the_id_and_name_in_creation_order(client: TestClient) -> None:
    created = [create(client, name).json() for name in ["z", "a", "m"]]

    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == created
    assert [dataset["name"] for dataset in response.json()] == ["z", "a", "m"]
    assert all(set(dataset) == {"id", "name"} for dataset in response.json())


def test_list_order_does_not_depend_on_where_the_rows_are_stored(
    client: TestClient, clean_database: DatabaseURL
) -> None:
    created = [create(client, name).json() for name in "abc"]

    # Rewrites the first row, so Postgres now finds it last when it scans the table.
    run_sql(clean_database, "UPDATE datasets SET name = name WHERE name = 'a'")

    assert client.get(URL).json() == created


def test_list_order_follows_the_creation_time(
    client: TestClient, clean_database: DatabaseURL
) -> None:
    created = [create(client, name).json() for name in "abc"]

    # The last row stays last on disk, so only the sort can move it to the front.
    run_sql(
        clean_database,
        "UPDATE datasets SET created_at = created_at - interval '1 day' "
        "WHERE name = 'c'",
    )

    assert client.get(URL).json() == [created[2], created[0], created[1]]


def test_list_order_of_datasets_created_at_the_same_moment_is_by_id(
    client: TestClient, clean_database: DatabaseURL
) -> None:
    created = [create(client, name).json() for name in "abcde"]

    run_sql(clean_database, "UPDATE datasets SET created_at = '2026-01-01'")

    ids = [dataset["id"] for dataset in client.get(URL).json()]
    assert ids == sorted(dataset["id"] for dataset in created)


def test_dataset_survives_an_app_restart(
    clean_database: DatabaseURL, start_app: StartApp
) -> None:
    with start_app() as before_restart:
        created = create(before_restart).json()

    with start_app() as after_restart:
        assert after_restart.get(URL).json() == [created]
        assert create(after_restart).status_code == 409
