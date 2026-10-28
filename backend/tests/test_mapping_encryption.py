from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from logsanitizer.mapping_store import (
    MappingEncryptionError,
    get_or_create_indexed_mapping,
    mapping_database_path,
    mapping_key_path,
)


def _legacy_database(path: Path, original_value: str, replacement: str = "[IP_1]") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute(
            """
            CREATE TABLE indexed_mappings (
                project_id TEXT NOT NULL,
                category TEXT NOT NULL,
                prefix TEXT NOT NULL,
                original_value TEXT NOT NULL,
                replacement TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK (sequence > 0),
                PRIMARY KEY (project_id, category, prefix, original_value),
                UNIQUE (project_id, category, prefix, sequence)
            )
            """
        )
        db.execute(
            "INSERT INTO indexed_mappings VALUES (?, ?, ?, ?, ?, ?)",
            ("project-1", "ip", "IP", original_value, replacement, 1),
        )


def test_mapping_values_are_encrypted_and_stable_across_calls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    secret = "10.123.45.67-sensitive-original"

    first = get_or_create_indexed_mapping("project-1", "ip", "IP", secret)
    second = get_or_create_indexed_mapping("project-1", "ip", "IP", secret)
    next_value = get_or_create_indexed_mapping("project-1", "ip", "IP", "10.123.45.68")

    assert first == second == "[IP_1]"
    assert next_value == "[IP_2]"
    assert mapping_key_path().is_file()
    assert len(mapping_key_path().read_bytes()) == 32
    assert secret.encode() not in mapping_database_path().read_bytes()

    with sqlite3.connect(mapping_database_path()) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(indexed_mappings)")}
        assert "original_value" not in columns
        assert {"value_hash", "encrypted_value"}.issubset(columns)


def test_legacy_plaintext_database_is_migrated_and_existing_replacements_preserved(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    path = mapping_database_path()
    secret = "legacy-sensitive-value"
    _legacy_database(path, secret)

    assert get_or_create_indexed_mapping("project-1", "ip", "IP", secret) == "[IP_1]"
    assert secret.encode() not in path.read_bytes()
    assert get_or_create_indexed_mapping("project-1", "ip", "IP", secret) == "[IP_1]"
    assert get_or_create_indexed_mapping("project-1", "ip", "IP", "new-value") == "[IP_2]"


def test_missing_key_for_encrypted_database_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    get_or_create_indexed_mapping("project-1", "user", "User", "alice")
    mapping_key_path().unlink()

    with pytest.raises(MappingEncryptionError, match="Schlüsseldatei fehlt"):
        get_or_create_indexed_mapping("project-1", "user", "User", "alice")

    assert not mapping_key_path().exists()


def test_wrong_key_fails_closed_without_creating_new_mappings(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    get_or_create_indexed_mapping("project-1", "token", "Token", "secret-token")
    mapping_key_path().write_bytes(b"x" * 32)

    with pytest.raises(MappingEncryptionError, match="passt nicht zu dieser Datenbank"):
        get_or_create_indexed_mapping("project-1", "token", "Token", "secret-token")


def test_posix_key_file_permissions_are_owner_only(tmp_path, monkeypatch) -> None:
    import os
    import stat

    if os.name == "nt":
        pytest.skip("Windows verwendet ACLs statt POSIX-Dateimodi.")
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    get_or_create_indexed_mapping("project-1", "host", "Host", "host.internal")
    assert stat.S_IMODE(mapping_key_path().stat().st_mode) == 0o600
