"""LDAP/Active Directory authentication for the network deployment profile."""
from __future__ import annotations

from typing import Any


class LDAPAuthenticationError(Exception):
    """LDAP credentials or directory configuration were rejected."""


def authenticate_ldap(username: str, password: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Verify credentials against LDAP and map direct group membership to LogSanitizer roles.

    LDAP is an optional dependency. This function never falls back to local-password
    authentication and never logs usernames, passwords, LDAP responses, or DNs.
    """
    try:
        from ldap3 import NONE, Connection, Server
        from ldap3.utils.conv import escape_filter_chars
    except ImportError as exc:
        raise LDAPAuthenticationError("LDAP-Unterstützung ist nicht installiert.") from exc

    config = settings["ldap"]
    username = username.strip()
    if not username or len(username) > 256 or not password:
        raise LDAPAuthenticationError("LDAP-Anmeldung abgelehnt.")
    template = str(config.get("user_filter", "(sAMAccountName={username})"))
    if "{username}" not in template or len(template) > 512:
        raise LDAPAuthenticationError("LDAP-Suchfilter ist ungültig.")
    search_filter = template.replace("{username}", escape_filter_chars(username))
    tls = bool(config.get("use_ssl"))
    server = Server(
        str(config["host"]),
        port=int(config.get("port", 636 if tls else 389)),
        use_ssl=tls,
        get_info=NONE,
        connect_timeout=5,
    )
    bind_password = __import__("os").environ.get("LOGSANITIZER_LDAP_BIND_PASSWORD", "")
    if not bind_password:
        raise LDAPAuthenticationError("LDAP-Anmeldung nicht verfügbar.")
    try:
        with Connection(
            server,
            user=str(config["bind_dn"]),
            password=bind_password,
            auto_bind=True,
            receive_timeout=5,
        ) as connection:
            attributes = [str(config.get("username_attribute", "sAMAccountName")),
                          str(config.get("group_attribute", "memberOf"))]
            if not connection.search(
                str(config["user_search_base"]),
                search_filter,
                attributes=attributes,
                size_limit=2,
            ) or len(connection.entries) != 1:
                raise LDAPAuthenticationError("LDAP-Anmeldung abgelehnt.")
            entry = connection.entries[0]
            user_dn = str(entry.entry_dn)
            canonical_username = str(entry[str(config.get("username_attribute", "sAMAccountName"))].value or username)
            groups = {
                str(value).casefold()
                for value in (entry[str(config.get("group_attribute", "memberOf"))].values or [])
            }
        with Connection(
            server,
            user=user_dn,
            password=password,
            auto_bind=True,
            receive_timeout=5,
        ):
            pass
        role_groups = config.get("role_groups", {})
        allowed_roles = {"admin", "operator", "reviewer", "approver"}
        roles = sorted(
            role for role, group_dn in role_groups.items()
            if role in allowed_roles and str(group_dn).casefold() in groups
        )
        if not roles:
            raise LDAPAuthenticationError("LDAP-Benutzer hat keine zugewiesene LogSanitizer-Rolle.")
        return {"username": canonical_username, "roles": roles}
    except LDAPAuthenticationError:
        raise
    except Exception as exc:
        # Avoid leaking provider details and credentials through API errors.
        raise LDAPAuthenticationError("LDAP-Anmeldung fehlgeschlagen.") from exc
