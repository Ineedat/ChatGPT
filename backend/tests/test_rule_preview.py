from pathlib import Path

from test_client import TestClient

from logsanitizer.main import app
from logsanitizer.rule_config import RuleConfig
from logsanitizer.rule_preview import preview_rules


def sample_config() -> RuleConfig:
    return RuleConfig.model_validate({
        "schema_version": 1,
        "profiles": [{"id": "web", "name": "Webserver"}],
        "rules": [
            {
                "id": "ip", "name": "IP-Adresse", "category": "IP",
                "match_type": "regex", "pattern": r"192\\.0\\.2\\.\\d+",
                "replacement": "[IP]", "replacement_mode": "indexed",
                "mapping_prefix": "IP", "priority": 10, "enabled": True,
            },
            {
                "id": "ip-tail", "name": "IP-Ende", "category": "Sonstiges",
                "match_type": "plain", "pattern": "[IP_1]",
                "replacement": "[MASKED]", "priority": 20, "enabled": True,
            },
            {
                "id": "email", "name": "E-Mail", "category": "E-Mail",
                "match_type": "regex", "pattern": r"[a-z]+@example\\.test",
                "replacement": "[EMAIL]", "priority": 30, "enabled": False,
            },
        ],
    })


def test_preview_applies_enabled_rules_in_priority_order_and_reports_chaining() -> None:
    result = preview_rules("client=192.0.2.17", sample_config())
    assert result["preview_text"] == "client=[MASKED]"
    assert [item["rule_id"] for item in result["rule_results"]] == ["ip", "ip-tail"]
    assert result["rule_results"][0]["matches"][0]["replacement"] == "[IP_1]"
    assert result["rule_results"][1]["matches"][0]["chained_from"] == ["ip"]


def test_single_rule_preview_tests_disabled_rule_and_does_not_mutate_config() -> None:
    config = sample_config()
    result = preview_rules("mail=alice@example.test", config, rule_id="email")
    assert result["preview_text"] == "mail=[EMAIL]"
    assert result["rule_results"][0]["enabled"] is False
    assert config.rules[2].enabled is False


def test_preview_reports_overlapping_initial_matches() -> None:
    data = sample_config().model_dump(mode="json")
    data["rules"] = [
        {"id": "one", "name": "One", "category": "x", "match_type": "plain",
         "pattern": "192.0", "replacement": "A", "priority": 10},
        {"id": "two", "name": "Two", "category": "x", "match_type": "plain",
         "pattern": "0.2", "replacement": "B", "priority": 20},
    ]
    result = preview_rules("192.0.2.17", RuleConfig.model_validate(data))
    assert result["overlaps"]
    assert result["overlaps"][0]["first_rule_id"] == "one"
    assert result["overlaps"][0]["second_rule_id"] == "two"


def test_preview_reuses_indexed_placeholder_without_touching_mapping_store(tmp_path, monkeypatch) -> None:
    mapping_dir = tmp_path / "mappings"
    monkeypatch.setenv("LOGSANITIZER_MAPPINGS_DIR", str(mapping_dir))
    result = preview_rules("192.0.2.17 192.0.2.17", sample_config())
    assert result["preview_text"] == "[MASKED] [MASKED]"
    assert not mapping_dir.exists()


def test_preview_rejects_oversized_sample_and_unknown_profile() -> None:
    config = sample_config()
    try:
        preview_rules("x" * 65_537, config)
        assert False, "expected size error"
    except ValueError as exc:
        assert "begrenzt" in str(exc)
    try:
        preview_rules("sample", config, profile_id="missing")
        assert False, "expected profile error"
    except ValueError as exc:
        assert "Quellprofil" in str(exc)


def test_rule_preview_api_is_non_persistent_and_returns_safe_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    monkeypatch.setenv("LOGSANITIZER_MAPPINGS_DIR", str(tmp_path / "mappings"))
    payload = {
        "config": sample_config().model_dump(mode="json"),
        "sample_text": "client=192.0.2.17",
        "profile_id": None,
    }
    with TestClient(app) as client:
        response = client.post("/api/rules/preview", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["preview_text"] == "client=[MASKED]"
        assert body["rule_results"][0]["match_count"] == 1
        assert not (tmp_path / "mappings").exists()
        assert not (tmp_path / "rules" / "rules-v1.json").exists()
