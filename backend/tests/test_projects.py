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
        assert metadata["format_hint"] == "text"
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


def test_folder_import_registers_files_and_reports_duplicates(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    folder = tmp_path / "logs"
    nested = folder / "nested"
    nested.mkdir(parents=True)
    first = folder / "one.log"
    second = nested / "two.log"
    first.write_text("token=secret-one", encoding="utf-8")
    second.write_text("token=secret-two", encoding="utf-8")
    first_before = first.read_bytes()
    second_before = second.read_bytes()

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Folder import"}).json()["id"]
        response = client.post(
            f"/api/projects/{project_id}/files/import-folder",
            json={"path": str(folder)},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["registered_count"] == 2
        assert result["skipped_count"] == 0
        assert {item["display_name"] for item in result["registered_files"]} == {
            "one.log",
            "two.log",
        }
        assert all("source_path" not in item for item in result["registered_files"])

        repeated = client.post(
            f"/api/projects/{project_id}/files/import-folder",
            json={"path": str(folder)},
        )
        assert repeated.status_code == 200
        assert repeated.json()["registered_count"] == 0
        assert repeated.json()["skipped_count"] == 2
        assert all("bereits" in issue["reason"].casefold() for issue in repeated.json()["issues"])

    assert first.read_bytes() == first_before
    assert second.read_bytes() == second_before


def test_folder_import_nonrecursive_and_invalid_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    folder = tmp_path / "logs"
    nested = folder / "nested"
    nested.mkdir(parents=True)
    (folder / "top.log").write_text("top", encoding="utf-8")
    (nested / "nested.log").write_text("nested", encoding="utf-8")

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Folder import"}).json()["id"]
        nonrecursive = client.post(
            f"/api/projects/{project_id}/files/import-folder",
            json={"path": str(folder), "recursive": False},
        )
        relative = client.post(
            f"/api/projects/{project_id}/files/import-folder",
            json={"path": "relative-folder"},
        )
        missing = client.post(
            f"/api/projects/{project_id}/files/import-folder",
            json={"path": str(tmp_path / "missing")},
        )
        file_path = client.post(
            f"/api/projects/{project_id}/files/import-folder",
            json={"path": str(folder / "top.log")},
        )

    assert nonrecursive.status_code == 200
    assert nonrecursive.json()["registered_count"] == 1
    assert nonrecursive.json()["registered_files"][0]["display_name"] == "top.log"
    assert relative.status_code == 422
    assert missing.status_code == 404
    assert file_path.status_code == 422



def test_format_hint_uses_extension_and_leaves_unknown_explicit(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    folder = tmp_path / "logs"
    folder.mkdir()
    for name in ("events.json", "events.ndjson", "report.xml", "table.csv", "opaque.data"):
        (folder / name).write_text("contents are not inspected", encoding="utf-8")

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Format hints"}).json()["id"]
        response = client.post(
            f"/api/projects/{project_id}/files/import-folder",
            json={"path": str(folder)},
        )

    assert response.status_code == 200
    hints = {item["display_name"]: item["format_hint"] for item in response.json()["registered_files"]}
    assert hints == {
        "events.json": "json",
        "events.ndjson": "jsonl",
        "report.xml": "xml",
        "table.csv": "csv",
        "opaque.data": "unknown",
    }


def test_local_format_detection_is_explicit_and_does_not_modify_source(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    source = tmp_path / "events.json"
    original = b'{"event":"started","count":1}\n'
    source.write_bytes(original)

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Detection"}).json()["id"]
        registered = client.post(f"/api/projects/{project_id}/files", json={"path": str(source)})
        file_id = registered.json()["id"]
        detected = client.post(f"/api/projects/{project_id}/files/{file_id}/detect-format")
        assert detected.status_code == 200
        assert detected.json()["detected_format"] == "json"
        assert detected.json()["sample_limit_bytes"] == "65536"
        assert "event" not in detected.text
        missing = client.post(f"/api/projects/{project_id}/files/missing/detect-format")
        assert missing.status_code == 404

    assert source.read_bytes() == original


def test_format_classifier_marks_jsonl_and_binary_unknown(tmp_path) -> None:
    from logsanitizer.main import detect_format_from_sample
    jsonl = tmp_path / "events.data"
    jsonl.write_text('{"event":1}\n{"event":2}\n', encoding="utf-8")
    assert detect_format_from_sample(jsonl) == "jsonl"
    binary = tmp_path / "opaque.log"
    binary.write_bytes(bytes([255, 0, 254]))
    assert detect_format_from_sample(binary) == "unknown"
