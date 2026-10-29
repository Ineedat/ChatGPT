import json
import os

import pytest
from fastapi.testclient import TestClient

from logsanitizer.deployment import DeploymentConfigError, load_settings
from logsanitizer.main import app


def _write_config(tmp_path, monkeypatch, value):
    path = tmp_path / "deployment.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setenv("LOGSANITIZER_CONFIG", str(path))
    return path


def test_missing_config_path_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_CONFIG", str(tmp_path / "missing.json"))
    with pytest.raises(DeploymentConfigError):
        load_settings()


def test_standalone_profile_is_local_and_disables_smtp(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, {
        "profile": "standalone",
        "server": {"bind_host": "127.0.0.1", "port": 8000, "tls_terminated": False},
        "auth": {"provider": "local"},
        "smtp": {"enabled": False},
    })
    monkeypatch.setenv("LOGSANITIZER_SMTP_HOST", "smtp.should-not-be-used.invalid")
    settings = load_settings()
    assert settings["profile"] == "standalone"
    assert settings["server"]["bind_host"] == "127.0.0.1"
    assert "LOGSANITIZER_SMTP_HOST" not in os.environ


def test_standalone_rejects_network_bind(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, {
        "profile": "standalone",
        "server": {"bind_host": "0.0.0.0"},
        "auth": {"provider": "local"},
    })
    with pytest.raises(DeploymentConfigError, match="Loopback"):
        load_settings()


def test_network_profile_requires_ldap_tls_and_bind_secret(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, {
        "profile": "network",
        "server": {"bind_host": "10.20.30.40", "port": 8000, "tls_terminated": True},
        "auth": {"provider": "ldap"},
        "ldap": {
            "enabled": True, "host": "ldap.example.invalid", "port": 636,
            "use_ssl": True, "start_tls": False,
            "bind_dn": "CN=reader,DC=example,DC=invalid",
            "user_search_base": "DC=example,DC=invalid",
            "role_groups": {"operator": "CN=Operators,DC=example,DC=invalid"},
        },
        "smtp": {"enabled": False},
    })
    monkeypatch.delenv("LOGSANITIZER_LDAP_BIND_PASSWORD", raising=False)
    with pytest.raises(DeploymentConfigError, match="BIND_PASSWORD"):
        load_settings()
    monkeypatch.setenv("LOGSANITIZER_LDAP_BIND_PASSWORD", "test-only-secret")
    settings = load_settings()
    assert settings["auth"]["provider"] == "ldap"
    assert os.environ["LOGSANITIZER_COOKIE_SECURE"] == "1"


def test_secrets_are_rejected_from_json_configuration(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, {
        "profile": "standalone",
        "server": {"bind_host": "127.0.0.1"},
        "auth": {"provider": "local"},
        "smtp": {"password": "do-not-commit"},
    })
    with pytest.raises(DeploymentConfigError, match="Geheimnisse"):
        load_settings()


def test_network_login_uses_ldap_only_and_sets_secure_cookie(tmp_path, monkeypatch):
    from logsanitizer import auth as auth_module

    _write_config(tmp_path, monkeypatch, {
        "profile": "network",
        "server": {"bind_host": "10.20.30.40", "port": 8000, "tls_terminated": True},
        "auth": {"provider": "ldap"},
        "ldap": {
            "enabled": True, "host": "ldap.example.invalid", "port": 636,
            "use_ssl": True, "start_tls": False,
            "bind_dn": "CN=reader,DC=example,DC=invalid",
            "user_search_base": "DC=example,DC=invalid",
            "role_groups": {"operator": "CN=Operators,DC=example,DC=invalid"},
        },
        "smtp": {"enabled": False},
    })
    monkeypatch.setenv("LOGSANITIZER_LDAP_BIND_PASSWORD", "test-only-secret")
    def fake_ldap(username, password, settings):
        if username == "directory-user" and password == "directory-password":
            return {"username": username, "roles": ["operator"]}
        raise auth_module.LDAPAuthenticationError("denied")
    monkeypatch.setattr(auth_module, "authenticate_ldap", fake_ldap)
    with TestClient(app) as client:
        denied = client.post("/api/auth/login", json={
            "username": "directory-user", "password": "wrong",
        })
        assert denied.status_code == 401
        success = client.post("/api/auth/login", json={
            "username": "directory-user", "password": "directory-password",
        })
        assert success.status_code == 200
        assert "secure" in success.headers["set-cookie"].casefold()
        assert client.get("/api/auth/me").json()["roles"] == ["operator"]
