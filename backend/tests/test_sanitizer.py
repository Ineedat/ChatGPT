from pathlib import Path

import pytest
from test_client import TestClient

from logsanitizer.main import app
from logsanitizer.rule_config import RuleConfig, save_rule_config
from logsanitizer.sanitizer import SanitizationCancelled, SanitizationError, sanitize_file


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
                "pattern": r"secret=(\w+)",
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
                "replacement": "[PROFILE_1]",
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
        "validated": True,
        "residual_matches": 0,
        "validation_scope": "configured_rules_and_format",
    }


def test_profile_rules_apply_only_when_selected(tmp_path: Path) -> None:
    source = tmp_path / "service.log"
    source.write_text("account=42\n", encoding="utf-8")
    shared_output = tmp_path / "shared.log"
    profile_output = tmp_path / "profile.log"

    sanitize_file(source, shared_output, config())
    sanitize_file(source, profile_output, config(), profile_id="payments")

    assert shared_output.read_text(encoding="utf-8") == "account=42\n"
    assert profile_output.read_text(encoding="utf-8") == "[PROFILE_1]=42\n"


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
            json={"output_path": str(tmp_path / "data" / "outputs" / "unsupported.log")},
        )
        assert unsupported.status_code == 422

        changed = client.put(
            f"/api/projects/{project_id}/files/{file['id']}/format",
            json={"format_override": "text"},
        )
        assert changed.status_code == 200
        response = client.post(
            f"/api/projects/{project_id}/files/{file['id']}/sanitize",
            json={"output_path": str(tmp_path / "data" / "outputs" / "clean.log")},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert response.json()["replacements"] == 2
        assert "secret" not in response.text

    assert (tmp_path / "data" / "outputs" / "clean.log").read_bytes() == b"hidden=REDACTED\n"
    assert source.read_bytes() == original


def test_jsonl_is_validated_before_and_after_rule_execution(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    original = b'{"message":"secret=alpha"}\n'
    source.write_bytes(original)
    destination = tmp_path / "clean.jsonl"

    result = sanitize_file(source, destination, config(), format_name="jsonl")

    assert destination.read_bytes() == b'{"message":"hidden=REDACTED"}\n'
    assert result["replacements"] == 2
    assert source.read_bytes() == original


def test_invalid_jsonl_is_rejected_and_partial_output_removed(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    original = b'{"message":"ok"}\nnot-json\n'
    source.write_bytes(original)
    destination = tmp_path / "clean.jsonl"

    with pytest.raises(SanitizationError, match="gültiges JSON"):
        sanitize_file(source, destination, config(), format_name="jsonl")

    assert not destination.exists()
    assert source.read_bytes() == original


def indexed_config() -> RuleConfig:
    data = config().model_dump(mode="json")
    data["rules"] = [{
        "id": "indexed-ip",
        "name": "Indexed IP",
        "category": "network",
        "match_type": "regex",
        "pattern": r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",
        "replacement": "[IP]",
        "replacement_mode": "indexed",
        "mapping_prefix": "IP",
        "priority": 10,
    }]
    return RuleConfig.model_validate(data)


def test_indexed_mapping_is_stable_across_files_and_isolated_by_project(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("LOGSANITIZER_MAPPINGS_DIR", str(tmp_path / "mappings"))
    cfg = indexed_config()
    first = tmp_path / "first.log"
    second = tmp_path / "second.log"
    third = tmp_path / "third.log"
    first.write_text("client=192.0.2.10 other=192.0.2.11\\n", encoding="utf-8")
    second.write_text("again=192.0.2.10\\n", encoding="utf-8")
    third.write_text("again=192.0.2.10\\n", encoding="utf-8")

    sanitize_file(first, tmp_path / "first.clean", cfg, project_id="project-a")
    sanitize_file(second, tmp_path / "second.clean", cfg, project_id="project-a")
    sanitize_file(third, tmp_path / "third.clean", cfg, project_id="project-b")

    assert (tmp_path / "first.clean").read_text(encoding="utf-8") == (
        "client=[IP_1] other=[IP_2]\\n"
    )
    assert (tmp_path / "second.clean").read_text(encoding="utf-8") == "again=[IP_1]\\n"
    assert (tmp_path / "third.clean").read_text(encoding="utf-8") == "again=[IP_1]\\n"
    assert first.read_text(encoding="utf-8") == "client=192.0.2.10 other=192.0.2.11\\n"
    assert second.read_text(encoding="utf-8") == "again=192.0.2.10\\n"


def test_indexed_mapping_requires_project_id(tmp_path: Path) -> None:
    source = tmp_path / "source.log"
    source.write_text("192.0.2.10\\n", encoding="utf-8")

    with pytest.raises(SanitizationError, match="Projekt-ID"):
        sanitize_file(source, tmp_path / "clean.log", indexed_config())

def test_residual_rule_match_rejects_and_removes_output_without_echoing_value(tmp_path: Path) -> None:
    source = tmp_path / "service.log"
    original = b"secret=alpha\\n"
    source.write_bytes(original)
    destination = tmp_path / "clean.log"
    data = config().model_dump(mode="json")
    data["rules"] = [data["rules"][0]]
    data["rules"][0]["replacement"] = "secret=still-present"
    unsafe_config = RuleConfig.model_validate(data)

    with pytest.raises(SanitizationError, match="Restmusterprüfung fehlgeschlagen") as error:
        sanitize_file(source, destination, unsafe_config)

    assert "alpha" not in str(error.value)
    assert not destination.exists()
    assert source.read_bytes() == original


def test_successful_scan_reports_validation_scope_and_zero_residuals(tmp_path: Path) -> None:
    source = tmp_path / "service.log"
    source.write_text("secret=alpha\\n", encoding="utf-8")
    destination = tmp_path / "clean.log"

    result = sanitize_file(source, destination, config())

    assert result["validated"] is True
    assert result["residual_matches"] == 0
    assert result["validation_scope"] == "configured_rules_and_format"


def test_residual_scan_rejects_invalid_jsonl_output_and_removes_it(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text('{"message":"safe"}\n', encoding="utf-8")
    destination = tmp_path / "clean.jsonl"
    data = config().model_dump(mode="json")
    data["rules"] = [data["rules"][0]]
    data["rules"][0]["pattern"] = "safe"
    data["rules"][0]["replacement"] = 'not-json"'
    unsafe_config = RuleConfig.model_validate(data)

    with pytest.raises(SanitizationError, match="ungültige JSON-Zeile"):
        sanitize_file(source, destination, unsafe_config, format_name="jsonl")

    assert not destination.exists()



def test_sanitizer_reports_progress_and_cleans_staging_file_on_cancel(tmp_path: Path) -> None:
    source = tmp_path / "large.log"
    source.write_text("first line\\nsecond line\\nthird line\\n", encoding="utf-8")
    destination = tmp_path / "clean.log"
    progress: list[dict[str, int | str]] = []

    def cancel_after_first_line(update: dict[str, int | str]) -> None:
        progress.append(update)

    def should_cancel() -> bool:
        return any(update.get("phase") == "sanitizing" for update in progress)

    with pytest.raises(SanitizationCancelled):
        sanitize_file(
            source,
            destination,
            config(),
            progress_callback=cancel_after_first_line,
            cancel_check=should_cancel,
        )

    assert progress
    assert progress[0]["processed_bytes"] > 0
    assert not destination.exists()
    assert list(tmp_path.glob(".clean.log.logsanitizer-*.tmp")) == []
    assert source.read_text(encoding="utf-8") == "first line\\nsecond line\\nthird line\\n"


def test_sanitization_job_api_reports_progress_and_completed_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(config())
    source = tmp_path / "service.log"
    original = b"secret=alpha\\n"
    source.write_bytes(original)

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Background sanitize"}).json()["id"]
        file = client.post(
            f"/api/projects/{project_id}/files", json={"path": str(source)}
        ).json()
        client.put(
            f"/api/projects/{project_id}/files/{file['id']}/format",
            json={"format_override": "text"},
        )
        outside_start = client.post(
            f"/api/projects/{project_id}/files/{file['id']}/sanitize-jobs",
            json={"output_path": str(tmp_path / "outside-job.log")},
        )
        assert outside_start.status_code == 422
        assert not (tmp_path / "outside-job.log").exists()

        output = tmp_path / "data" / "outputs" / "job-clean.log"
        started = client.post(
            f"/api/projects/{project_id}/files/{file['id']}/sanitize-jobs",
            json={"output_path": str(output)},
        )
        assert started.status_code == 202
        job_id = started.json()["id"]
        status_response = client.get(
            f"/api/projects/{project_id}/files/{file['id']}/sanitize-jobs/{job_id}"
        )
        assert status_response.status_code == 200
        state = status_response.json()
        assert state["status"] == "completed"
        assert state["phase"] == "completed"
        assert state["processed_bytes"] == output.stat().st_size
        assert state["total_bytes"] == output.stat().st_size
        assert state["result"]["validated"] is True
        assert "source_path" not in status_response.text
        assert "secret=alpha" not in status_response.text

    assert output.read_bytes() == b"hidden=REDACTED\\n"
    assert source.read_bytes() == original
    assert list(tmp_path.glob(".job-clean.log.logsanitizer-*.tmp")) == []


def test_pathological_regex_times_out_and_partial_output_is_removed(tmp_path: Path) -> None:
    source = tmp_path / "pathological.log"
    source.write_text("a" * 100_000 + "!\\n", encoding="utf-8")
    destination = tmp_path / "clean.log"
    unsafe_config = RuleConfig.model_validate({
        "schema_version": 1,
        "rules": [{
            "id": "pathological",
            "name": "Pathological regex",
            "category": "test",
            "match_type": "regex",
            "pattern": r"(a+)+$",
            "replacement": "REDACTED",
            "priority": 1,
        }],
    })

    with pytest.raises(SanitizationError, match="Zeitlimit"):
        sanitize_file(source, destination, unsafe_config)

    assert not destination.exists()
    assert list(tmp_path.glob(".clean.log.logsanitizer-*.tmp")) == []



def test_sanitization_api_rejects_output_outside_configured_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(config())
    source = tmp_path / "outside-source.log"
    source.write_text("secret=value\\n", encoding="utf-8")
    outside = tmp_path / "outside.log"

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Workspace boundary"}).json()["id"]
        imported = client.post(
            f"/api/projects/{project_id}/files", json={"path": str(source)}
        ).json()
        client.put(
            f"/api/projects/{project_id}/files/{imported['id']}/format",
            json={"format_override": "text"},
        )
        response = client.post(
            f"/api/projects/{project_id}/files/{imported['id']}/sanitize",
            json={"output_path": str(outside)},
        )
        assert response.status_code == 422
        assert not outside.exists()


def test_workspace_resolver_rejects_traversal_and_symlinked_directory(tmp_path: Path) -> None:
    from logsanitizer.output_workspace import OutputWorkspaceError, resolve_output_path

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(OutputWorkspaceError):
        resolve_output_path("../outside.log", workspace)

    actual = tmp_path / "actual"
    actual.mkdir()
    link = workspace / "linked"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are unavailable for this test account/platform")
    with pytest.raises(OutputWorkspaceError):
        resolve_output_path("linked/out.log", workspace)
