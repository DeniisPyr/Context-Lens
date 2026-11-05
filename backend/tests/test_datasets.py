from concurrent.futures import ThreadPoolExecutor
from unittest.mock import ANY
from uuid import UUID, uuid4

import pytest
from conftest import StartApp, create_dataset, run_sql
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import URL as DatabaseURL

URL = "/api/datasets"
TAKEN = {"detail": "A dataset with this name already exists."}
NO_SUCH_DATASET = "00000000-0000-0000-0000-000000000000"


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


BAD_DATASET_IDS = [
    "unknown",
    "not-a-uuid",
    "123",
    "00000000-0000-0000-0000-00000000000g",
    "0" * 33,
    "%00",
    "%20",
    "é",
    NO_SUCH_DATASET,
    str(uuid4()),
]
NOT_FOUND = {"detail": "Dataset not found."}


def upload(
    client: TestClient,
    documents_url: str,
    filename: str = "notes.txt",
    content: bytes = b"hello\n",
) -> Response:
    return client.post(documents_url, files={"file": (filename, content)})


def test_upload_into_a_dataset_returns_the_summary_and_lists_it(
    client: TestClient, documents_url: str
) -> None:
    response = upload(client, documents_url, "poznámky.txt", b"a\nb\n")

    assert response.status_code == 201
    assert response.json() == {"id": ANY, "filename": "poznámky.txt", "line_count": 2}
    assert client.get(documents_url).json() == [response.json()]


def test_uploaded_document_can_be_read_by_its_own_id(
    client: TestClient, documents_url: str
) -> None:
    uploaded = upload(client, documents_url, "a.txt", b"one\ntwo\n").json()

    response = client.get(f"/api/documents/{uploaded['id']}")

    assert response.status_code == 200
    assert response.json() == {**uploaded, "lines": ["one", "two"]}


def test_uploaded_document_can_be_asked_about(
    client: TestClient, documents_url: str
) -> None:
    uploaded = upload(client, documents_url, "a.txt", b"The cat is orange.\n").json()

    response = client.post(
        "/api/ask", json={"document_id": uploaded["id"], "question": "Which colour?"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["citations"][0]["filename"] == "a.txt"


def test_list_of_an_empty_dataset_is_empty(
    client: TestClient, documents_url: str
) -> None:
    response = client.get(documents_url)

    assert response.status_code == 200
    assert response.json() == []


def test_list_holds_the_summaries_in_upload_order_and_no_text(
    client: TestClient, documents_url: str
) -> None:
    uploads = [upload(client, documents_url, f"{name}.txt").json() for name in "zam"]

    response = client.get(documents_url)

    assert response.json() == uploads
    assert all(
        set(item) == {"id", "filename", "line_count"} for item in response.json()
    )


def test_list_holds_only_the_documents_of_that_dataset(client: TestClient) -> None:
    reports_url = create_dataset(client, "Reports")
    invoices_url = create_dataset(client, "Invoices")
    empty_url = create_dataset(client, "Empty")
    report = upload(client, reports_url, "report.txt").json()
    invoice = upload(client, invoices_url, "invoice.txt").json()

    assert client.get(reports_url).json() == [report]
    assert client.get(invoices_url).json() == [invoice]
    assert client.get(empty_url).json() == []


def test_duplicate_filename_in_a_dataset_is_a_conflict(
    client: TestClient, documents_url: str
) -> None:
    first = upload(client, documents_url, "notes.txt", b"first version\n").json()

    response = upload(client, documents_url, "notes.txt", b"second version\n")

    assert response.status_code == 409
    assert response.json() == {"detail": "notes.txt is already in this dataset."}
    assert client.get(documents_url).json() == [first]
    assert client.get(f"/api/documents/{first['id']}").json()["lines"] == [
        "first version"
    ]


def test_filename_is_compared_after_the_path_is_removed(
    client: TestClient, documents_url: str
) -> None:
    upload(client, documents_url, "notes.txt")

    response = upload(client, documents_url, "C:\\docs\\notes.txt")

    assert response.status_code == 409
    assert response.json() == {"detail": "notes.txt is already in this dataset."}


def test_filenames_differing_only_in_case_are_different_filenames(
    client: TestClient, documents_url: str
) -> None:
    upload(client, documents_url, "notes.txt")

    assert upload(client, documents_url, "NOTES.txt").status_code == 201


def test_same_filename_in_another_dataset_is_a_separate_document(
    client: TestClient,
) -> None:
    reports_url = create_dataset(client, "Reports")
    invoices_url = create_dataset(client, "Invoices")

    in_reports = upload(client, reports_url, "notes.txt", b"from reports\n")
    in_invoices = upload(client, invoices_url, "notes.txt", b"from invoices\n")

    assert in_reports.status_code == 201
    assert in_invoices.status_code == 201
    assert in_reports.json()["id"] != in_invoices.json()["id"]
    assert client.get(f"/api/documents/{in_reports.json()['id']}").json()["lines"] == [
        "from reports"
    ]
    assert client.get(f"/api/documents/{in_invoices.json()['id']}").json()["lines"] == [
        "from invoices"
    ]


def test_only_one_of_many_uploads_racing_for_a_filename_wins(
    client: TestClient, documents_url: str
) -> None:
    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(
            executor.map(lambda _: upload(client, documents_url), range(8))
        )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [201] + [409] * 7
    assert len(client.get(documents_url).json()) == 1


@pytest.mark.parametrize("dataset_id", BAD_DATASET_IDS)
def test_upload_to_a_bad_or_unknown_dataset_is_a_404(
    client: TestClient, documents_url: str, dataset_id: str
) -> None:
    response = upload(client, f"{URL}/{dataset_id}/documents")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND
    assert client.get(documents_url).json() == []


@pytest.mark.parametrize("dataset_id", BAD_DATASET_IDS)
def test_list_of_a_bad_or_unknown_dataset_is_a_404(
    client: TestClient, documents_url: str, dataset_id: str
) -> None:
    upload(client, documents_url)

    response = client.get(f"{URL}/{dataset_id}/documents")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


@pytest.mark.parametrize(
    ("dataset_id", "filename", "content", "status"),
    [
        ("not-a-uuid", "notes.pdf", b"hello", 415),
        ("not-a-uuid", "notes.txt", b"caf\xe9", 415),
        ("not-a-uuid", "notes.txt", b"", 422),
        ("not-a-uuid", "notes.txt", b"x" * 1_000_001, 413),
        (NO_SUCH_DATASET, "notes.pdf", b"hello", 415),
        (NO_SUCH_DATASET, "notes.txt", b"", 422),
    ],
)
def test_the_file_is_checked_before_the_dataset(
    client: TestClient, dataset_id: str, filename: str, content: bytes, status: int
) -> None:
    response = upload(client, f"{URL}/{dataset_id}/documents", filename, content)

    assert response.status_code == status


def test_the_file_is_checked_before_its_filename_is_compared(
    client: TestClient, documents_url: str
) -> None:
    upload(client, documents_url, "notes.txt")

    response = upload(client, documents_url, "notes.txt", b"")

    assert response.status_code == 422


def test_upload_without_a_file_is_a_validation_error(
    client: TestClient, documents_url: str
) -> None:
    response = client.post(documents_url)

    assert response.status_code == 422
    assert client.get(documents_url).json() == []


@pytest.mark.parametrize(
    ("method", "request_parts"),
    [
        ("GET", {}),
        ("POST", {"files": {"file": ("a.txt", b"hello")}}),
    ],
    ids=["list", "upload"],
)
def test_the_old_document_routes_are_gone(
    client: TestClient, method: str, request_parts: dict
) -> None:
    response = client.request(method, "/api/documents", **request_parts)

    assert response.status_code in {404, 405}
