from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from logsanitizer.main import app
from logsanitizer.rule_config import RuleConfig, save_rule_config
from logsanitizer.sanitizer import SanitizationError, sanitize_file


def config() -> RuleConfig:
    return RuleConfig.model_validate({
        "schema_version": 1,
        "profiles": [{"id": "payments", "name": "Payments"}],
        "rules": [
            {
                "id": "token-value",
                "name": "Token value",
                "category": "secret",
                "match_type": "regex",
                "pattern": r"secret=(\\w+)",
                "replacement": "token=REDACTED",
                "priority": 20,
            },
            {
                "id": "token-key",
                "name": "Token key",
                "category": "secret",
                "match_type": "plain",
                "pattern": "token",
                "replacement": "hidden",
                "priority": 30,
            },
            {
                "id": "profile-only",
                "name": "Profile-only",
                "category": "secret",
                "match_type": "plain",
                "pattern": "account",
                "replacement": "[ACCOUNT]",
                "priority": 10,
                "profile_id": "payments",
            },
        ],
    })


def test_streaming_sanitizer_orders_rules_and_preserves_source(tmp_path: Path) -> None:
    source = tmp_path / "service.log"
    original = b"secret=alpha\r\naccount=42\nplain text\n"
    source.write_bytes(original)
    destination = tmp_path / "clean.log"

    result = sanitize_file(source, destination, config())

    assert destination.read_bytes() == b"hidden=REDACTED\r\naccount=42\nplain text\n"
    assert source.read_bytes() == original
    assert result == {
        "status": "completed",
        "input_bytes": len(original),
        "output_bytes": len(destination.read_bytes()),
        "lines_processed": 3,
        "replacements": 2,
    }


def test_profile_rules_apply_only_when_selected(tmp_path: Path) -> None:
    source = tmp_path / "service.log"
    source.write_text("account=42\n", encoding="utf-8")
    shared_output = tmp_path / "shared.log"
    profile_output = tmp_path / "profile.log"

    sanitize_file(source, shared_output, config())
    sanitize_file(source, profile_output, config(), profile_id="payments")

    assert shared_output.read_text(encoding="utf-8") == "account=42\n"
    assert profile_output.read_text(encoding="utf-8") == "[ACCOUNT]=42\n"


def test_sanitizer_refuses_existing_destination_and_invalid_profile(tmp_path: Path) -> None:
    source = tmp_path / "service.log"
    source.write_text("secret=value\n", encoding="utf-8")
    destination = tmp_path / "clean.log"
    destination.write_text("keep me", encoding="utf-8")

    with pytest.raises(FileExistsError):
        sanitize_file(source, destination, config())
    with pytest.raises(SanitizationError, match="Quellprofil"):
        sanitize_file(source, tmp_path / "other.log", config(), profile_id="missing")

    assert destination.read_text(encoding="utf-8") == "keep me"
    assert source.read_text(encoding="utf-8") == "secret=value\n"


def test_sanitizer_removes_partial_output_after_invalid_utf8(tmp_path: Path) -> None:
    source = tmp_path / "service.log"
    source.write_bytes(b"secret=value\ninvalid=\xff\n")
    destination = tmp_path / "clean.log"

    with pytest.raises(SanitizationError, match="UTF-8"):
        sanitize_file(source, destination, config())

    assert not destination.exists()
    assert source.read_bytes() == b"secret=value\ninvalid=\xff\n"


def test_sanitization_api_requires_selected_supported_format_and_writes_separately(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(config())
    source = tmp_path / "service.log"
    original = b"secret=alpha\n"
    source.write_bytes(original)

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Sanitize"}).json()["id"]
        file = client.post(
            f"/api/projects/{project_id}/files", json={"path": str(source)}
        ).json()
        unsupported = client.post(
            f"/api/projects/{project_id}/files/{file['id']}/sanitize",
            json={"output_path": str(tmp_path / "unsupported.log")},
        )
        assert unsupported.status_code == 422

        changed = client.put(
            f"/api/projects/{project_id}/files/{file['id']}/format",
            json={"format_override": "text"},
        )
        assert changed.status_code == 200
        response = client.post(
            f"/api/projects/{project_id}/files/{file['id']}/sanitize",
            json={"output_path": str(tmp_path / "clean.log")},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert response.json()["replacements"] == 1
        assert "secret" not in response.text

    assert (tmp_path / "clean.log").read_bytes() == b"token=REDACTED\n"
    assert source.read_bytes() == original
