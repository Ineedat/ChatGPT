from test_client import TestClient

from logsanitizer.format_validation import validate_file
from logsanitizer.main import app


def test_streaming_validator_accepts_supported_formats(tmp_path) -> None:
    examples = {
        "text": ("service.log", "line one\nline two\n"),
        "json": ("events.json", '{"event":"start","items":[1,true,null]}'),
        "jsonl": ("events.jsonl", '{"event":1}\n{"event":2}\n'),
        "xml": ("events.xml", '<?xml version="1.0"?><events><event id="1"/></events>'),
        "csv": ("events.csv", "name,count\nalpha,1\nbeta,2\n"),
    }
    for format_name, (filename, value) in examples.items():
        path = tmp_path / filename
        path.write_text(value, encoding="utf-8")
        result = validate_file(path, format_name)
        assert result["valid"] is True, (format_name, result)
        assert result["bytes_checked"] == path.stat().st_size


def test_streaming_validator_rejects_invalid_files_without_echoing_contents(tmp_path) -> None:
    cases = {
        "json": '{"token":"super-secret",}',
        "jsonl": '{"event":1}\nnot-json\n',
        "xml": "<events><event></events>",
        "csv": '"unterminated field',
        "text": b"invalid utf-8: \xff",
    }
    for format_name, value in cases.items():
        path = tmp_path / f"invalid.{format_name}"
        path.write_bytes(value if isinstance(value, bytes) else value.encode("utf-8"))
        result = validate_file(path, format_name)
        assert result["valid"] is False
        assert result["error"]
        assert "super-secret" not in str(result)


def test_json_validation_handles_large_stream_and_rejects_trailing_data(tmp_path) -> None:
    path = tmp_path / "large.json"
    path.write_text('{"events":[' + ",".join('{"n":1}' for _ in range(20000)) + "]}", encoding="utf-8")
    assert validate_file(path, "json")["valid"] is True
    path.write_text('{"ok":true} trailing', encoding="utf-8")
    assert validate_file(path, "json")["valid"] is False


def test_unknown_format_is_not_treated_as_valid(tmp_path) -> None:
    path = tmp_path / "opaque.data"
    path.write_text("maybe anything", encoding="utf-8")
    result = validate_file(path, "unknown")
    assert result["valid"] is False
    assert "explizit auswählen" in result["error"]


def test_validation_endpoint_uses_manual_override_and_keeps_original(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    source = tmp_path / "misleading.log"
    original = b'{"ok":true}'
    source.write_bytes(original)

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Validation"}).json()["id"]
        registered = client.post(
            f"/api/projects/{project_id}/files", json={"path": str(source)}
        ).json()
        file_id = registered["id"]
        selected = client.put(
            f"/api/projects/{project_id}/files/{file_id}/format",
            json={"format_override": "json"},
        )
        assert selected.status_code == 200
        result = client.post(
            f"/api/projects/{project_id}/files/{file_id}/validate-format"
        )
        assert result.status_code == 200
        assert result.json()["valid"] is True
        assert result.json()["format"] == "json"
        assert result.json()["bytes_checked"] == len(original)
        missing = client.post(
            f"/api/projects/{project_id}/files/not-a-file/validate-format"
        )
        assert missing.status_code == 404

    assert source.read_bytes() == original


def test_bounded_detection_recognizes_large_json_documents_and_jsonl(tmp_path):
    from logsanitizer.main import detect_format_from_sample

    document = tmp_path / "large-document.json"
    document.write_text('{"events":[\n' + ",".join('{"message":"event-%05d"}' % i for i in range(5000)) + "\n]}", encoding="utf-8")
    assert document.stat().st_size > 64 * 1024
    assert detect_format_from_sample(document) == "json"

    lines = tmp_path / "large-events.jsonl"
    lines.write_text("".join('{"event":%d}\n' % i for i in range(10000)), encoding="utf-8")
    assert lines.stat().st_size > 64 * 1024
    assert detect_format_from_sample(lines) == "jsonl"
