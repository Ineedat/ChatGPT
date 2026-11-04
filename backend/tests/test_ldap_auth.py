from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from logsanitizer.ldap_auth import LDAPAuthenticationError, authenticate_ldap


def _fake_ldap3(monkeypatch, *, accepted_user_password="personal-password"):
    binds = []
    searches = []

    class FakeConnection:
        def __init__(self, server, user, password, **kwargs):
            self.user = user
            self.password = password
            self.entries = []
            binds.append((user, password))

        def open(self):
            return True

        def start_tls(self):
            return True

        def bind(self):
            if self.user == "CN=reader,DC=example,DC=invalid":
                return self.password == "service-password"
            return self.password == accepted_user_password

        def search(self, base, search_filter, attributes, size_limit):
            searches.append((base, search_filter, attributes, size_limit))
            self.entries = [
                SimpleNamespace(
                    entry_dn="CN=Alice,OU=Users,DC=example,DC=invalid",
                    __getitem__=None,
                )
            ]
            entry = self.entries[0]

            class Attribute:
                value = "alice"
                values = ["CN=LogSanitizer-Operators,OU=Groups,DC=example,DC=invalid"]

            entry.__class__ = type(
                "FakeEntry",
                (),
                {
                    "entry_dn": entry.entry_dn,
                    "__getitem__": lambda self, key: Attribute(),
                },
            )
            self.entries = [entry]
            return True

        def unbind(self):
            return True

    ldap3 = types.ModuleType("ldap3")
    ldap3.NONE = object()
    ldap3.Connection = FakeConnection
    ldap3.Server = lambda *args, **kwargs: object()
    ldap3.Tls = lambda **kwargs: kwargs
    utils = types.ModuleType("ldap3.utils")
    conv = types.ModuleType("ldap3.utils.conv")
    conv.escape_filter_chars = lambda value: value.replace("*", r"\\2a")
    monkeypatch.setitem(sys.modules, "ldap3", ldap3)
    monkeypatch.setitem(sys.modules, "ldap3.utils", utils)
    monkeypatch.setitem(sys.modules, "ldap3.utils.conv", conv)
    return binds, searches


def _settings():
    return {
        "ldap": {
            "host": "dc01.example.invalid",
            "port": 636,
            "use_ssl": True,
            "start_tls": False,
            "ca_certs_file": "",
            "bind_dn": "CN=reader,DC=example,DC=invalid",
            "user_search_base": "OU=Users,DC=example,DC=invalid",
            "user_filter": "(sAMAccountName={username})",
            "username_attribute": "sAMAccountName",
            "group_attribute": "memberOf",
            "role_groups": {
                "operator": "CN=LogSanitizer-Operators,OU=Groups,DC=example,DC=invalid"
            },
        }
    }


def test_ldap_login_binds_with_personal_user_password(monkeypatch):
    binds, searches = _fake_ldap3(monkeypatch)
    monkeypatch.setenv("LOGSANITIZER_LDAP_BIND_PASSWORD", "service-password")

    identity = authenticate_ldap("alice", "personal-password", _settings())

    assert identity == {"username": "alice", "roles": ["operator"]}
    assert binds == [
        ("CN=reader,DC=example,DC=invalid", "service-password"),
        ("CN=Alice,OU=Users,DC=example,DC=invalid", "personal-password"),
    ]
    assert searches[0][1] == "(sAMAccountName=alice)"


def test_ldap_login_rejects_wrong_personal_user_password(monkeypatch):
    _fake_ldap3(monkeypatch)
    monkeypatch.setenv("LOGSANITIZER_LDAP_BIND_PASSWORD", "service-password")

    with pytest.raises(LDAPAuthenticationError, match="LDAP-Anmeldung abgelehnt"):
        authenticate_ldap("alice", "wrong-personal-password", _settings())
