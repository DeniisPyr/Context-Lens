from fastapi.testclient import TestClient


def test_health_returns_ok_with_the_database_unreachable(
    client_without_database: TestClient,
) -> None:
    response = client_without_database.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
