"""Deployment profile loading and fail-closed validation.

The configuration file contains deployment metadata only. Bind passwords and SMTP
passwords are supplied through environment variables, never the portable bundle.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "profile": "standalone",
    "server": {"bind_host": "127.0.0.1", "port": 8000, "tls_terminated": False},
    "auth": {"provider": "local"},
    "ldap": {
        "enabled": False,
        "host": "",
        "port": 636,
        "use_ssl": True,
        "start_tls": False,
        "bind_dn": "",
        "user_search_base": "",
        "user_filter": "(sAMAccountName={username})",
        "username_attribute": "sAMAccountName",
        "group_attribute": "memberOf",
        "role_groups": {},
    },
    "smtp": {
        "enabled": False,
        "host": "",
        "port": 587,
        "security": "starttls",
        "from": "",
        "reviewer_emails": "",
        "operator_emails": "",
    },
}


class DeploymentConfigError(ValueError):
    """Deployment configuration is unsafe or inconsistent."""


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _config_path() -> Path | None:
    configured = os.environ.get("LOGSANITIZER_CONFIG")
    if configured:
        return Path(configured).expanduser()
    candidates = (
        Path.cwd() / "config" / "deployment.json",
        Path(__file__).resolve().parents[3] / "config" / "deployment.json",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def load_settings() -> dict[str, Any]:
    """Load the optional JSON file, then apply secret environment overrides."""
    settings = dict(DEFAULTS)
    settings = _merge(settings, {key: dict(value) for key, value in DEFAULTS.items() if isinstance(value, dict)})
    path = _config_path()
    if path is not None:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DeploymentConfigError("Deployment-Konfiguration kann nicht gelesen werden.") from exc
        if not isinstance(loaded, dict):
            raise DeploymentConfigError("Deployment-Konfiguration muss ein JSON-Objekt sein.")
        forbidden = {"password", "bind_password", "smtp_password", "secret", "client_secret"}
        def reject_secrets(value: Any) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    if key.casefold() in forbidden:
                        raise DeploymentConfigError(
                            "Geheimnisse gehören nicht in die JSON-Konfiguration, sondern in Umgebungsvariablen."
                        )
                    reject_secrets(nested)
            elif isinstance(value, list):
                for nested in value:
                    reject_secrets(nested)
        reject_secrets(loaded)
        settings = _merge(settings, loaded)

    profile = settings.get("profile")
    server = settings.get("server", {})
    auth = settings.get("auth", {})
    ldap = settings.get("ldap", {})
    smtp = settings.get("smtp", {})
    if profile not in {"standalone", "network"}:
        raise DeploymentConfigError("Profil muss 'standalone' oder 'network' sein.")
    if not isinstance(server.get("port"), int) or not 1 <= server["port"] <= 65535:
        raise DeploymentConfigError("Server-Port muss zwischen 1 und 65535 liegen.")
    if auth.get("provider") not in {"local", "ldap"}:
        raise DeploymentConfigError("Authentifizierungsanbieter muss 'local' oder 'ldap' sein.")
    if profile == "standalone":
        if smtp.get("enabled"):
            raise DeploymentConfigError("SMTP ist im Standalone-Profil deaktiviert.")
        if server.get("bind_host") not in {"127.0.0.1", "::1", "localhost"}:
            raise DeploymentConfigError("Standalone muss auf Loopback beschränkt bleiben.")
        if auth.get("provider") != "local":
            raise DeploymentConfigError("Standalone unterstützt ausschließlich lokale Anmeldung.")
    else:
        if auth.get("provider") != "ldap" or ldap.get("enabled") is not True:
            raise DeploymentConfigError("Netzwerkprofil erfordert aktiviertes LDAP als Anmeldeanbieter.")
        if server.get("bind_host") in {"127.0.0.1", "::1", "localhost", ""}:
            raise DeploymentConfigError("Netzwerkprofil benötigt eine explizite Netzwerk-Bind-Adresse.")
        if server.get("tls_terminated") is not True:
            raise DeploymentConfigError("Netzwerkprofil erfordert HTTPS/TLS-Terminierung.")
        if not os.environ.get("LOGSANITIZER_LDAP_BIND_PASSWORD"):
            raise DeploymentConfigError("LOGSANITIZER_LDAP_BIND_PASSWORD ist nicht gesetzt.")
        if not ldap.get("host") or not ldap.get("bind_dn") or not ldap.get("user_search_base"):
            raise DeploymentConfigError("LDAP-Host, Bind-DN und User-Search-Base sind erforderlich.")
        if not isinstance(ldap.get("role_groups"), dict) or not ldap["role_groups"]:
            raise DeploymentConfigError("LDAP-Rollengruppen müssen explizit konfiguriert sein.")
    if ldap.get("enabled") and ldap.get("use_ssl") is True and ldap.get("start_tls") is True:
        raise DeploymentConfigError("LDAP LDAPS und StartTLS dürfen nicht gleichzeitig aktiviert sein.")
    if ldap.get("enabled") and ldap.get("use_ssl") is not True and ldap.get("start_tls") is not True:
        raise DeploymentConfigError("LDAP benötigt LDAPS oder StartTLS; unverschlüsseltes LDAP ist nicht zulässig.")
    if smtp.get("enabled"):
        if not smtp.get("host") or not smtp.get("from"):
            raise DeploymentConfigError("Aktiviertes SMTP benötigt Host und Absenderadresse.")
        if smtp.get("security") not in {"starttls", "ssl", "none"}:
            raise DeploymentConfigError("SMTP-Sicherheit muss starttls, ssl oder none sein.")
        if not isinstance(smtp.get("port"), int) or not 1 <= smtp["port"] <= 65535:
            raise DeploymentConfigError("SMTP-Port muss zwischen 1 und 65535 liegen.")
    smtp_env_names = (
        "LOGSANITIZER_SMTP_HOST", "LOGSANITIZER_SMTP_PORT", "LOGSANITIZER_SMTP_SECURITY",
        "LOGSANITIZER_SMTP_FROM", "LOGSANITIZER_REVIEWER_EMAILS", "LOGSANITIZER_OPERATOR_EMAILS",
        "LOGSANITIZER_SMTP_USERNAME", "LOGSANITIZER_SMTP_PASSWORD",
    )
    if profile == "standalone" or not smtp.get("enabled"):
        for env_name in smtp_env_names:
            os.environ.pop(env_name, None)
    for key, env_name in (
        ("host", "LOGSANITIZER_SMTP_HOST"),
        ("port", "LOGSANITIZER_SMTP_PORT"),
        ("security", "LOGSANITIZER_SMTP_SECURITY"),
        ("from", "LOGSANITIZER_SMTP_FROM"),
        ("reviewer_emails", "LOGSANITIZER_REVIEWER_EMAILS"),
        ("operator_emails", "LOGSANITIZER_OPERATOR_EMAILS"),
    ):
        if smtp.get("enabled") and env_name not in os.environ:
            os.environ[env_name] = str(smtp.get(key, ""))
    return settings


def server_bind() -> tuple[str, int]:
    settings = load_settings()
    return str(settings["server"]["bind_host"]), int(settings["server"]["port"])
