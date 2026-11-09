import logging
import re
import time
from collections.abc import Iterator

import pytest
from conftest import StartApp
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from httpx2 import Response
from pydantic import SecretStr
from sqlalchemy import URL

from context_lens.services.sessions import SESSION_SECONDS, sign_session

PASSWORD = "correct horse battery staple"
OLD_PASSWORD = "an old password"
COOKIE = "context_lens_session"
NOT_LOGGED_IN = {"detail": "Log in first."}
WRONG_PASSWORD = {"detail": "Wrong password."}
WARNING = (
    "ACCESS_PASSWORD isn't set, so anyone who can reach the app can read every "
    "document and spend the Gemini credits."
)
# Every session cookie has these, and Secure as well when SECURE_COOKIES is set.
COOKIE_ATTRIBUTES = {
    "httponly": "",
    "max-age": "43200",
    "path": "/api",
    "samesite": "strict",
}
OPEN_PATHS = {"/api/health", "/api/session"}

NO_SUCH_ID = "00000000-0000-0000-0000-000000000000"
NO_SUCH_DATASET_DOCUMENTS = f"/api/datasets/{NO_SUCH_ID}/documents"
UPLOAD = {"files": {"file": ("notes.txt", b"The cat is orange.")}}
PROTECTED_ROUTES = [
    pytest.param("GET", "/api/datasets", {}, id="list_datasets"),
    pytest.param("POST", "/api/datasets", {"json": {"name": "A"}}, id="create_dataset"),
    pytest.param("DELETE", f"/api/datasets/{NO_SUCH_ID}", {}, id="delete_dataset"),
    pytest.param("GET", NO_SUCH_DATASET_DOCUMENTS, {}, id="list_documents"),
    pytest.param("POST", NO_SUCH_DATASET_DOCUMENTS, UPLOAD, id="upload"),
    pytest.param("GET", f"/api/documents/{NO_SUCH_ID}", {}, id="read_document"),
    pytest.param("DELETE", f"/api/documents/{NO_SUCH_ID}", {}, id="delete_document"),
    pytest.param(
        "POST",
        "/api/ask",
        {"json": {"dataset_id": NO_SUCH_ID, "question": "Hi"}},
        id="ask",
    ),
]

# Signed when the tests are collected, which is well within the twelve hours.
SESSION = sign_session(SecretStr(PASSWORD), time.time())
EXPIRY, SIGNATURE = SESSION.split(".")
CHANGED_SIGNATURE = SIGNATURE[:-1] + ("1" if SIGNATURE[-1] == "0" else "0")
FORGED_SESSIONS = [
    pytest.param(
        sign_session(SecretStr(PASSWORD), time.time() - SESSION_SECONDS - 1),
        id="expired",
    ),
    pytest.param(f"{int(EXPIRY) + SESSION_SECONDS}.{SIGNATURE}", id="later_expiry"),
    pytest.param(f"{EXPIRY}.{CHANGED_SIGNATURE}", id="changed_signature"),
    pytest.param(sign_session(SecretStr(OLD_PASSWORD), time.time()), id="old_password"),
    pytest.param(f"{EXPIRY}.{'0' * 64}", id="zero_signature"),
    pytest.param("junk", id="junk"),
]
# Sent as bytes, so that they reach the app exactly as written.
MALFORMED_COOKIE_HEADERS = [
    pytest.param(b"context_lens_session=", id="empty"),
    pytest.param(b"context_lens_session", id="no_value"),
    pytest.param(b'context_lens_session=""', id="empty_quotes"),
    pytest.param(b"context_lens_session=\xc3\xa9\xff\xfe", id="non_ascii"),
    pytest.param(b"context_lens_session=1.\xc3\xa9\xff", id="non_ascii_signature"),
    pytest.param(b'context_lens_session="1.\\"2\\""', id="quoted"),
    pytest.param(b"context_lens_session=1.2.3.4", id="dots"),
    pytest.param(b"context_lens_session=" + b"9" * 4000, id="very_long"),
    pytest.param(b"=;;==; context_lens_session=%%%", id="broken_pairs"),
    pytest.param(b"context_lens_session=1; context_lens_session=2", id="twice"),
]


@pytest.fixture
def password_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACCESS_PASSWORD", PASSWORD)


@pytest.fixture
def guarded(password_set: None, start_app: StartApp) -> Iterator[TestClient]:
    # Without a database: a request without a session must be turned away before it
    # would reach one.
    with start_app() as client:
        yield client


@pytest.fixture
def guarded_with_database(
    password_set: None, clean_database: URL, start_app: StartApp
) -> Iterator[TestClient]:
    with start_app() as client:
        yield client


def log_in(client: TestClient, password: str = PASSWORD) -> Response:
    return client.post("/api/session", json={"password": password})


def with_cookie(session: str) -> dict[str, str]:
    return {"cookie": f"{COOKIE}={session}"}


def set_cookie(response: Response) -> tuple[str, dict[str, str]]:
    [header] = response.headers.get_list("set-cookie")
    pair, *attributes = header.split("; ")
    name, _, value = pair.partition("=")
    assert name == COOKIE
    parsed = {}
    for attribute in attributes:
        key, _, setting = attribute.partition("=")
        parsed[key.lower()] = setting
    return value, parsed


def logged_in(client: TestClient) -> bool:
    return client.get("/api/session").json()["logged_in"]


def main_logs(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "context_lens.main"]


def test_without_a_password_no_login_is_required(
    client_without_database: TestClient,
) -> None:
    response = client_without_database.get("/api/session")

    assert response.status_code == 200
    assert response.json() == {"login_required": False, "logged_in": True}


def test_without_a_password_the_routes_need_no_session(client: TestClient) -> None:
    created = client.post("/api/datasets", json={"name": "Reports"})

    assert created.status_code == 201
    assert client.get("/api/datasets").json() == [created.json()]


def test_without_a_password_logging_in_sets_no_cookie(
    client_without_database: TestClient,
) -> None:
    response = log_in(client_without_database, "anything")

    assert response.status_code == 204
    assert "set-cookie" not in response.headers
    assert logged_in(client_without_database)


def test_with_a_password_a_login_is_required(guarded: TestClient) -> None:
    response = guarded.get("/api/session")

    assert response.status_code == 200
    assert response.json() == {"login_required": True, "logged_in": False}


def test_right_password_logs_in(guarded: TestClient) -> None:
    response = log_in(guarded)

    assert response.status_code == 204
    assert response.content == b""
    assert guarded.get("/api/session").json() == {
        "login_required": True,
        "logged_in": True,
    }


def test_right_password_sets_the_session_cookie(guarded: TestClient) -> None:
    before = int(time.time())

    session, attributes = set_cookie(log_in(guarded))

    assert attributes == COOKIE_ATTRIBUTES
    expiry, signature = session.split(".")
    assert before + SESSION_SECONDS <= int(expiry) <= time.time() + SESSION_SECONDS
    assert re.fullmatch("[0-9a-f]{64}", signature)


def test_secure_cookies_makes_the_cookie_secure(
    password_set: None, monkeypatch: pytest.MonkeyPatch, start_app: StartApp
) -> None:
    monkeypatch.setenv("SECURE_COOKIES", "true")

    with start_app() as client:
        _, attributes = set_cookie(log_in(client))
        _, expired = set_cookie(client.delete("/api/session"))

    assert attributes == {**COOKIE_ATTRIBUTES, "secure": ""}
    assert "secure" in expired


@pytest.mark.parametrize(
    "attempt",
    [
        pytest.param("wrong", id="other"),
        pytest.param(OLD_PASSWORD, id="old_password"),
        pytest.param(PASSWORD.upper(), id="upper_case"),
        pytest.param(PASSWORD[:-1], id="prefix"),
        pytest.param(PASSWORD + "e", id="longer"),
        pytest.param(" " + PASSWORD, id="leading_space"),
        pytest.param(PASSWORD + " ", id="trailing_space"),
        pytest.param("x" * 1000, id="1000_characters"),
    ],
)
def test_wrong_password_is_a_401(guarded: TestClient, attempt: str) -> None:
    response = log_in(guarded, attempt)

    assert response.status_code == 401
    assert response.json() == WRONG_PASSWORD
    assert "set-cookie" not in response.headers
    assert not logged_in(guarded)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="no_password"),
        pytest.param({"password": ""}, id="empty"),
        pytest.param({"password": "x" * 1001}, id="1001_characters"),
        pytest.param({"password": None}, id="null"),
        pytest.param({"password": 5}, id="number"),
        pytest.param({"password": [PASSWORD]}, id="list"),
        pytest.param({"secret": PASSWORD}, id="other_field"),
    ],
)
def test_login_without_a_text_password_is_a_validation_error(
    guarded: TestClient, body: dict
) -> None:
    response = guarded.post("/api/session", json=body)

    assert response.status_code == 422
    assert "set-cookie" not in response.headers
    assert not logged_in(guarded)


def test_password_of_1000_characters_logs_in(
    monkeypatch: pytest.MonkeyPatch, start_app: StartApp
) -> None:
    password = "ž" * 1000
    monkeypatch.setenv("ACCESS_PASSWORD", password)

    with start_app() as client:
        assert log_in(client, password).status_code == 204
        assert logged_in(client)


def test_logging_out_expires_the_cookie(guarded: TestClient) -> None:
    log_in(guarded)

    response = guarded.delete("/api/session")

    assert response.status_code == 204
    session, attributes = set_cookie(response)
    assert session in ("", '""')
    assert attributes["max-age"] == "0"
    assert {name: attributes[name] for name in ("path", "httponly", "samesite")} == {
        "path": "/api",
        "httponly": "",
        "samesite": "strict",
    }
    assert "secure" not in attributes
    assert not logged_in(guarded)
    assert guarded.get("/api/datasets").json() == NOT_LOGGED_IN


def test_logging_out_without_a_password_expires_the_cookie(
    client_without_database: TestClient,
) -> None:
    response = client_without_database.delete("/api/session")

    assert response.status_code == 204
    assert set_cookie(response)[1]["max-age"] == "0"


def test_health_needs_no_session(guarded: TestClient) -> None:
    response = guarded.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/docs", "/openapi.json"])
def test_api_docs_stay_as_they_are(guarded: TestClient, path: str) -> None:
    # They are outside /api, so the proxy in front of the app decides who sees them.
    assert guarded.get(path).status_code == 200


@pytest.mark.parametrize(("method", "path", "request_parts"), PROTECTED_ROUTES)
def test_every_protected_route_needs_a_session(
    guarded: TestClient, method: str, path: str, request_parts: dict
) -> None:
    response = guarded.request(method, path, **request_parts)

    assert response.status_code == 401
    assert response.json() == NOT_LOGGED_IN


def test_every_api_route_but_health_and_the_session_needs_a_session(
    guarded: TestClient,
) -> None:
    # Walks the routes the app really has, through the routers that include them, so
    # that a router added later without the session fails here though no test knows it.
    protected, open_paths = [], set()
    for route in iter_route_contexts(guarded.app.routes):
        if not route.path.startswith("/api/"):
            continue
        path = re.sub(r"\{[^}]+\}", NO_SUCH_ID, route.path)
        for method in route.methods:
            response = guarded.request(method, path)
            if route.path in OPEN_PATHS:
                open_paths.add(route.path)
                assert response.status_code != 401, (method, route.path)
            else:
                protected.append((method, route.path))
                assert response.status_code == 401, (method, route.path)
                assert response.json() == NOT_LOGGED_IN

    assert open_paths == OPEN_PATHS
    assert len(protected) >= len(PROTECTED_ROUTES)


def test_every_protected_route_works_after_logging_in(
    guarded_with_database: TestClient,
) -> None:
    client = guarded_with_database
    assert log_in(client).status_code == 204

    created = client.post("/api/datasets", json={"name": "Reports"})
    assert created.status_code == 201
    dataset_id = created.json()["id"]
    assert client.get("/api/datasets").status_code == 200
    uploaded = client.post(f"/api/datasets/{dataset_id}/documents", **UPLOAD)
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]
    assert client.get(f"/api/datasets/{dataset_id}/documents").status_code == 200
    assert client.get(f"/api/documents/{document_id}").status_code == 200
    asked = client.post(
        "/api/ask", json={"dataset_id": dataset_id, "question": "Which cat?"}
    )
    assert asked.status_code == 200
    assert asked.json()["status"] == "answered"
    assert client.delete(f"/api/documents/{document_id}").status_code == 204
    assert client.delete(f"/api/datasets/{dataset_id}").status_code == 204


def test_request_without_a_session_changes_nothing(
    guarded_with_database: TestClient,
) -> None:
    response = guarded_with_database.post("/api/datasets", json={"name": "Reports"})

    assert response.status_code == 401
    log_in(guarded_with_database)
    assert guarded_with_database.get("/api/datasets").json() == []


@pytest.mark.parametrize("session", FORGED_SESSIONS)
def test_forged_or_expired_session_is_a_401(guarded: TestClient, session: str) -> None:
    response = guarded.get("/api/datasets", headers=with_cookie(session))

    assert response.status_code == 401
    assert response.json() == NOT_LOGGED_IN
    assert guarded.get("/api/session", headers=with_cookie(session)).json() == {
        "login_required": True,
        "logged_in": False,
    }


@pytest.mark.parametrize("header", MALFORMED_COOKIE_HEADERS)
def test_malformed_cookie_is_a_401_rather_than_an_error(
    guarded: TestClient, header: bytes
) -> None:
    response = guarded.get("/api/datasets", headers={"cookie": header})
    session = guarded.get("/api/session", headers={"cookie": header})

    assert response.status_code == 401
    assert response.json() == NOT_LOGGED_IN
    assert session.status_code == 200
    assert session.json()["logged_in"] is False


def test_session_still_works_after_a_restart(
    password_set: None, clean_database: URL, start_app: StartApp
) -> None:
    with start_app() as client:
        session, _ = set_cookie(log_in(client))

    with start_app() as client:
        response = client.get("/api/datasets", headers=with_cookie(session))

    assert response.status_code == 200


def test_changing_the_password_ends_every_session(
    monkeypatch: pytest.MonkeyPatch, start_app: StartApp
) -> None:
    monkeypatch.setenv("ACCESS_PASSWORD", OLD_PASSWORD)
    with start_app() as client:
        session, _ = set_cookie(log_in(client, OLD_PASSWORD))

    monkeypatch.setenv("ACCESS_PASSWORD", PASSWORD)
    with start_app() as client:
        response = client.get("/api/datasets", headers=with_cookie(session))

    assert response.status_code == 401
    assert response.json() == NOT_LOGGED_IN


def test_password_and_session_are_never_logged_or_sent_back(
    guarded: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    responses = [log_in(guarded, "not the password"), log_in(guarded)]
    session, _ = set_cookie(responses[-1])
    # Without a database this logs the error, which must not quote the request.
    responses.append(guarded.get("/api/datasets"))
    responses.append(guarded.get("/api/datasets", headers=with_cookie(SIGNATURE)))
    responses.append(guarded.delete("/api/session"))

    assert responses[2].status_code == 503
    assert caplog.records
    for text in (PASSWORD, session, SIGNATURE):
        assert text not in caplog.text
    for response in responses:
        assert PASSWORD not in response.text
        assert PASSWORD not in str(response.headers)


def test_without_a_password_starting_the_app_warns_once(
    start_app: StartApp, caplog: pytest.LogCaptureFixture
) -> None:
    with start_app() as client:
        client.get("/api/health")
        client.get("/api/session")
        log_in(client, "anything")

    [record] = main_logs(caplog)
    assert record.levelname == "WARNING"
    assert record.getMessage() == WARNING
    assert "test-key" not in caplog.text


def test_with_a_password_starting_the_app_does_not_warn(
    password_set: None, start_app: StartApp, caplog: pytest.LogCaptureFixture
) -> None:
    with start_app() as client:
        log_in(client)

    assert main_logs(caplog) == []
