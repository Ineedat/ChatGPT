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


def test_register_source_file_keeps_original_unchanged(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    source = tmp_path / "service.log"
    original = b"host=app01 token=secret-value\nsecond line\n"
    source.write_bytes(original)

    with TestClient(app) as client:
        project_response = client.post("/api/projects", json={"name": "Incident"})
        project_id = project_response.json()["id"]
        imported = client.post(
            f"/api/projects/{project_id}/files",
            json={"path": str(source)},
        )

        assert imported.status_code == 201
        metadata = imported.json()
        assert metadata["display_name"] == "service.log"
        assert metadata["size_bytes"] == len(original)
        assert metadata["state"] == "registered"
        assert "source_path" not in metadata
        assert str(source) not in imported.text

        listed = client.get(f"/api/projects/{project_id}/files")
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        assert listed.json()[0]["id"] == metadata["id"]

    assert source.read_bytes() == original


def test_register_rejects_missing_file_and_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    folder = tmp_path / "folder"
    folder.mkdir()

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Incident"}).json()["id"]
        missing = client.post(
            f"/api/projects/{project_id}/files",
            json={"path": str(tmp_path / "missing.log")},
        )
        directory = client.post(
            f"/api/projects/{project_id}/files",
            json={"path": str(folder)},
        )

    assert missing.status_code == 404
    assert directory.status_code == 422


def test_register_rejects_relative_paths_and_symlinks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    source = tmp_path / "service.log"
    source.write_text("do not modify", encoding="utf-8")
    link = tmp_path / "linked.log"
    try:
        link.symlink_to(source)
    except OSError:
        link = None

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Incident"}).json()["id"]
        relative = client.post(
            f"/api/projects/{project_id}/files",
            json={"path": "service.log"},
        )
        linked = (
            client.post(f"/api/projects/{project_id}/files", json={"path": str(link)})
            if link is not None
            else None
        )

    assert relative.status_code == 422
    if linked is not None:
        assert linked.status_code == 422
    assert source.read_text(encoding="utf-8") == "do not modify"


def test_file_registration_requires_existing_project(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    source = tmp_path / "service.log"
    source.write_text("untouched", encoding="utf-8")

    with TestClient(app) as client:
        response = client.post(
            "/api/projects/not-a-project/files",
            json={"path": str(source)},
        )

    assert response.status_code == 404
