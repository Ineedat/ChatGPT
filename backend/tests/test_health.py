from fastapi.testclient import TestClient

from logsanitizer.main import app


def test_health_endpoint_returns_minimal_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "application": "LogSanitizer"}


def test_openapi_is_available_under_api_prefix(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    with TestClient(app) as client:
        response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "LogSanitizer API"
