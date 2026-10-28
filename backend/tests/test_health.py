from fastapi.testclient import TestClient

from logsanitizer.auth import create_user
from logsanitizer.main import app


def test_health_endpoint_returns_minimal_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "application": "LogSanitizer"}


def test_openapi_requires_authentication_and_is_available_after_login(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    create_user("docs-user", "docs-user-password-123", ["operator"])
    with TestClient(app) as client:
        assert client.get("/api/openapi.json").status_code == 401
        login = client.post(
            "/api/auth/login",
            json={"username": "docs-user", "password": "docs-user-password-123"},
        )
        assert login.status_code == 200
        response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "LogSanitizer API"
