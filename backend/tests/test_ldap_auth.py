from __future__ import annotations

import sys
import types
from typing import ClassVar

import pytest

from logsanitizer.ldap_auth import LDAPAuthenticationError, authenticate_ldap


def _fake_ldap3(monkeypatch, *, accepted_user_password="personal-password"):
    binds = []
    searches = []
    events = []

    class Attribute:
        value = "alice"
        values: ClassVar[list[str]] = ["CN=LogSanitizer-Operators,OU=Groups,DC=example,DC=invalid"]

    class FakeEntry:
        entry_dn = "CN=Alice,OU=Users,DC=example,DC=invalid"

        def __getitem__(self, key):
            return Attribute()

    class FakeConnection:
        def __init__(self, server, user, password, **kwargs):
            self.user = user
            self.password = password
            self.entries = []
            binds.append((user, password))

        def open(self):
            events.append(("open", self.user))
            return True

        def start_tls(self):
            events.append(("start_tls", self.user))
            return True

        def bind(self):
            events.append(("bind", self.user))
            if self.user == "CN=reader,DC=example,DC=invalid":
                return self.password == "service-password"
            return self.password == accepted_user_password

        def search(self, base, search_filter, attributes, size_limit):
            searches.append((base, search_filter, attributes, size_limit))
            self.entries = [FakeEntry()]
            return True

        def unbind(self):
            return True

    def fake_server(*args, **kwargs):
        return object()

    def fake_tls(**kwargs):
        return kwargs

    def escape_filter_chars(value):
        replacements = {"\\": r"\5c", "*": r"\2a", "(": r"\28", ")": r"\29", "\x00": r"\00"}
        return "".join(replacements.get(character, character) for character in value)

    ldap3 = types.ModuleType("ldap3")
    ldap3.__path__ = []
    ldap3.NONE = object()
    ldap3.Connection = FakeConnection
    ldap3.Server = fake_server
    ldap3.Tls = fake_tls
    utils = types.ModuleType("ldap3.utils")
    utils.__path__ = []
    conv = types.ModuleType("ldap3.utils.conv")
    conv.escape_filter_chars = escape_filter_chars
    ldap3.utils = utils
    utils.conv = conv
    monkeypatch.setitem(sys.modules, "ldap3", ldap3)
    monkeypatch.setitem(sys.modules, "ldap3.utils", utils)
    monkeypatch.setitem(sys.modules, "ldap3.utils.conv", conv)
    return binds, searches, events


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
    binds, searches, _events = _fake_ldap3(monkeypatch)
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


def test_ldap_starttls_is_negotiated_before_both_password_binds(monkeypatch):
    binds, _searches, events = _fake_ldap3(monkeypatch)
    monkeypatch.setenv("LOGSANITIZER_LDAP_BIND_PASSWORD", "service-password")
    settings = _settings()
    settings["ldap"]["use_ssl"] = False
    settings["ldap"]["start_tls"] = True

    authenticate_ldap("alice", "personal-password", settings)

    assert len(binds) == 2
    for user in ("CN=reader,DC=example,DC=invalid", "CN=Alice,OU=Users,DC=example,DC=invalid"):
        sequence = [event[0] for event in events if event[1] == user]
        assert sequence.index("start_tls") < sequence.index("bind")


def test_ldap_username_is_escaped_before_search(monkeypatch):
    _binds, searches, _events = _fake_ldap3(monkeypatch)
    monkeypatch.setenv("LOGSANITIZER_LDAP_BIND_PASSWORD", "service-password")

    authenticate_ldap("alice*)(uid=*)", "personal-password", _settings())

    assert searches[0][1] == r"(sAMAccountName=alice\2a\29\28uid=\2a\29)"
