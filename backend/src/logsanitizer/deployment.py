"""Deployment profile loading and fail-closed validation.

The configuration file contains deployment metadata only. Bind passwords and SMTP
passwords are supplied through environment variables, never the portable bundle.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "profile": "standalone",
    "data_dir": "",
    "server": {"bind_host": "127.0.0.1", "port": 8000, "tls_certfile": "", "tls_keyfile": ""},
    "auth": {"provider": "local"},
    "ldap": {
        "enabled": False,
        "host": "",
        "port": 636,
        "use_ssl": True,
        "start_tls": False,
        "ca_certs_file": "",
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
        Path(sys.executable).resolve().parent / "config" / "deployment.json",
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
                    if key.casefold() in forbidden or any(marker in key.casefold() for marker in ("password", "secret", "token")):
                        raise DeploymentConfigError(
                            "Geheimnisse gehören nicht in die JSON-Konfiguration, sondern in Umgebungsvariablen."
                        )
                    reject_secrets(nested)
            elif isinstance(value, list):
                for nested in value:
                    reject_secrets(nested)
        reject_secrets(loaded)
        settings = _merge(settings, loaded)
        server_config = settings.get("server", {})
        for key in ("tls_certfile", "tls_keyfile"):
            configured_path = server_config.get(key)
            if configured_path:
                certificate_path = Path(str(configured_path)).expanduser()
                if not certificate_path.is_absolute():
                    certificate_path = path.parent / certificate_path
                server_config[key] = str(certificate_path.resolve())
        data_dir = str(settings.get("data_dir") or "").strip()
        if data_dir:
            resolved_data = Path(data_dir).expanduser()
            if not resolved_data.is_absolute():
                resolved_data = path.parent / resolved_data
            settings["data_dir"] = str(resolved_data.resolve())
        ldap_config = settings.get("ldap", {})
        ca_path = ldap_config.get("ca_certs_file")
        if ca_path:
            resolved_ca = Path(str(ca_path)).expanduser()
            if not resolved_ca.is_absolute():
                resolved_ca = path.parent / resolved_ca
            ldap_config["ca_certs_file"] = str(resolved_ca.resolve())

    if settings.get("data_dir") and "LOGSANITIZER_DATA_DIR" not in os.environ:
        os.environ["LOGSANITIZER_DATA_DIR"] = str(settings["data_dir"])

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
        certfile = server.get("tls_certfile")
        keyfile = server.get("tls_keyfile")
        if not certfile or not keyfile or not Path(str(certfile)).is_file() or not Path(str(keyfile)).is_file():
            raise DeploymentConfigError("Netzwerkprofil benötigt vorhandene TLS-Zertifikats- und Schlüsseldateien.")
        if not os.environ.get("LOGSANITIZER_LDAP_BIND_PASSWORD"):
            raise DeploymentConfigError("LOGSANITIZER_LDAP_BIND_PASSWORD ist nicht gesetzt.")
        if not ldap.get("host") or not ldap.get("bind_dn") or not ldap.get("user_search_base"):
            raise DeploymentConfigError("LDAP-Host, Bind-DN und User-Search-Base sind erforderlich.")
        if not isinstance(ldap.get("role_groups"), dict) or not ldap["role_groups"]:
            raise DeploymentConfigError("LDAP-Rollengruppen müssen explizit konfiguriert sein.")
        ca_file = str(ldap.get("ca_certs_file") or "").strip()
        if ca_file and not Path(ca_file).is_file():
            raise DeploymentConfigError("Die konfigurierte LDAP-CA-Datei wurde nicht gefunden.")
    if ldap.get("enabled") and ldap.get("use_ssl") is True and ldap.get("start_tls") is True:
        raise DeploymentConfigError("LDAP LDAPS und StartTLS dürfen nicht gleichzeitig aktiviert sein.")
    if ldap.get("enabled") and ldap.get("use_ssl") is not True and ldap.get("start_tls") is not True:
        raise DeploymentConfigError("LDAP benötigt LDAPS oder StartTLS; unverschlüsseltes LDAP ist nicht zulässig.")
    if smtp.get("enabled"):
        if not smtp.get("host") or not smtp.get("from"):
            raise DeploymentConfigError("Aktiviertes SMTP benötigt Host und Absenderadresse.")
        if smtp.get("security") not in {"starttls", "ssl"}:
            raise DeploymentConfigError("Netzwerk-SMTP muss STARTTLS oder SSL verwenden.")
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
