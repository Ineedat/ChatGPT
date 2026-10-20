from fastapi.testclient import TestClient

from logsanitizer.main import app

client = TestClient(app)


def test_health_endpoint_returns_minimal_status() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "application": "LogSanitizer"}


def test_openapi_is_available_under_api_prefix() -> None:
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "LogSanitizer API"
