from fastapi.testclient import TestClient


def test_health_returns_ok_with_the_database_unreachable(
    client_without_database: TestClient,
) -> None:
    response = client_without_database.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_answers_while_the_routes_that_need_the_database_fail(
    client_without_database: TestClient,
) -> None:
    assert client_without_database.get("/api/documents").status_code == 503
    assert client_without_database.get("/api/health").status_code == 200
