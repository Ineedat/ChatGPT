import pytest
from pydantic import ValidationError
from test_client import TestClient

from logsanitizer.auth import create_user
from logsanitizer.main import app
from logsanitizer.rule_config import (
    RuleConfig,
    find_rule_conflicts,
    load_rule_config,
    save_rule_config,
)


def sample_config() -> dict:
    return {
        "schema_version": 1,
        "profiles": [{"id": "payments", "name": "Payments", "source_hint": "payment-service"}],
        "rules": [
            {
                "id": "ip-address",
                "name": "IP-Adresse",
                "category": "network",
                "match_type": "regex",
                "pattern": r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",
                "replacement": "[IP]",
                "case_sensitive": False,
                "priority": 10,
            },
            {
                "id": "payment-token",
                "name": "Payment token",
                "category": "secret",
                "match_type": "plain",
                "pattern": "payment-token=",
                "replacement": "payment-token=[REDACTED]",
                "case_sensitive": True,
                "priority": 20,
                "profile_id": "payments",
            },
        ],
    }


def test_rule_config_supports_shared_and_profile_rules_and_round_trips(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    config = RuleConfig.model_validate(sample_config())
    save_rule_config(config)

    loaded = load_rule_config()
    assert loaded.schema_version == 1
    assert loaded.rules[0].match_type == "regex"
    assert loaded.rules[0].priority == 10
    assert loaded.rules[0].profile_id is None
    assert loaded.rules[1].profile_id == "payments"
    saved_file = tmp_path / "rules" / "rules-v1.json"
    assert saved_file.exists()


def test_rule_config_rejects_unknown_schema_fields_bad_regex_and_missing_profile() -> None:
    with pytest.raises(ValidationError):
        RuleConfig.model_validate({"schema_version": 2, "rules": []})
    invalid_regex = sample_config()
    invalid_regex["rules"][0]["pattern"] = "("
    with pytest.raises(ValidationError, match="Ungültiger regulärer Ausdruck"):
        RuleConfig.model_validate(invalid_regex)
    missing_profile = sample_config()
    missing_profile["rules"][1]["profile_id"] = "unknown"
    with pytest.raises(ValidationError, match="nicht definiertes Quellprofil"):
        RuleConfig.model_validate(missing_profile)


def test_rule_conflicts_require_same_scope_pattern_and_priority() -> None:
    data = sample_config()
    duplicate = dict(data["rules"][0])
    duplicate["id"] = "ip-address-copy"
    duplicate["name"] = "Duplicate IP"
    data["rules"].append(duplicate)
    config = RuleConfig.model_validate(data)
    conflicts = find_rule_conflicts(config)
    assert conflicts == [{
        "rule_id": "ip-address-copy",
        "conflicts_with": "ip-address",
        "reason": "Gleiches Suchmuster, gleicher Geltungsbereich und gleiche Priorität.",
    }]


def test_rule_api_validates_and_persists_only_conflict_free_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    with TestClient(app) as client:
        validation = client.post("/api/rules/config/validate", json=sample_config())
        assert validation.status_code == 200
        assert validation.json()["valid"] is True
        assert validation.json()["conflicts"] == []

        saved = client.put("/api/rules/config", json=sample_config())
        assert saved.status_code == 200
        assert saved.json()["schema_version"] == 1
        assert client.get("/api/rules/config").json()["rules"][1]["profile_id"] == "payments"

        conflicting = sample_config()
        duplicate = dict(conflicting["rules"][0])
        duplicate["id"] = "duplicate"
        duplicate["name"] = "Duplicate"
        conflicting["rules"].append(duplicate)
        checked = client.post("/api/rules/config/validate", json=conflicting)
        assert checked.status_code == 200
        assert checked.json()["valid"] is False
        assert len(checked.json()["conflicts"]) == 1
        rejected = client.put("/api/rules/config", json=conflicting)
        assert rejected.status_code == 409
        assert "conflicts_with" in rejected.text

        invalid = client.put("/api/rules/config", json={"schema_version": 2, "rules": []})
        assert invalid.status_code == 422


def test_rule_management_permissions_allow_admin_and_rule_owner_but_deny_operator(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    create_user("rule-admin", "admin-password-123", ["admin"])
    create_user("rule-owner", "owner-password-123", ["rule_owner"])
    create_user("rule-processor", "processor-password-123", ["operator"])

    for username, password, expected in (
        ("rule-admin", "admin-password-123", 200),
        ("rule-owner", "owner-password-123", 200),
        ("rule-processor", "processor-password-123", 403),
    ):
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": username, "password": password})
            assert login.status_code == 200
            csrf = client.cookies.get("logsanitizer_csrf")
            response = client.put(
                "/api/rules/config",
                json=sample_config(),
                headers={"X-CSRF-Token": csrf},
            )
            assert response.status_code == expected

    with TestClient(app) as client:
        client.post("/api/auth/login", json={"username": "rule-processor", "password": "processor-password-123"})
        assert client.post("/api/rules/config/validate", json=sample_config()).status_code == 403
        assert client.post("/api/rules/preview", json={"config": sample_config(), "sample_text": "client=10.0.0.1"}).status_code == 403

def test_rule_library_api_returns_templates_without_changing_active_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    with TestClient(app) as client:
        response = client.get("/api/rules/library")
        assert response.status_code == 200
        body = response.json()
        assert len(body["categories"]) == 8
        assert len(body["templates"]) == 20
        assert all(template["enabled"] is False for template in body["templates"])
        assert not (tmp_path / "rules" / "rules-v1.json").exists()
