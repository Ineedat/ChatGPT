from fastapi.testclient import TestClient

from logsanitizer.main import app


def test_project_create_list_and_open_use_sqlite(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))

    with TestClient(app) as client:
        created = client.post(
            "/api/projects",
            json={"name": "  Incident 42  ", "description": "  App logs  "},
        )
        assert created.status_code == 201
        project = created.json()
        assert project["name"] == "Incident 42"
        assert project["description"] == "App logs"
        assert project["status"] == "draft"
        assert project["id"]

        listed = client.get("/api/projects")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [project["id"]]

        opened = client.get(f"/api/projects/{project['id']}")
        assert opened.status_code == 200
        assert opened.json() == project

    assert (tmp_path / "private-data" / "logsanitizer.sqlite3").is_file()


def test_project_name_must_not_be_blank(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))

    with TestClient(app) as client:
        response = client.post("/api/projects", json={"name": "   "})

    assert response.status_code == 422


def test_missing_project_returns_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))

    with TestClient(app) as client:
        response = client.get("/api/projects/not-a-project")

    assert response.status_code == 404
