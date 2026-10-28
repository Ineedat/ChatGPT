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



def test_mapping_backup_requires_and_recovers_with_database_and_key_pair(tmp_path, monkeypatch) -> None:
    import shutil

    original_dir = tmp_path / "original"
    recovery_dir = tmp_path / "recovery"
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(original_dir))
    expected = get_or_create_indexed_mapping("project-1", "ip", "IP", "192.0.2.25")
    recovery_dir.mkdir()
    shutil.copy2(mapping_database_path(), recovery_dir / "mappings.sqlite3")
    shutil.copy2(mapping_key_path(), recovery_dir / "mappings.key")

    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(recovery_dir))
    assert get_or_create_indexed_mapping("project-1", "ip", "IP", "192.0.2.25") == expected
    assert get_or_create_indexed_mapping("project-1", "ip", "IP", "192.0.2.26") == "[IP_2]"


def test_tampered_ciphertext_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    get_or_create_indexed_mapping("project-1", "token", "Token", "secret-token")
    with sqlite3.connect(mapping_database_path()) as db:
        ciphertext = db.execute(
            "SELECT encrypted_value FROM indexed_mappings WHERE project_id='project-1'"
        ).fetchone()[0]
        altered = bytearray(ciphertext)
        altered[-1] ^= 0x01
        db.execute(
            "UPDATE indexed_mappings SET encrypted_value=? WHERE project_id='project-1'",
            (bytes(altered),),
        )

    with pytest.raises(MappingEncryptionError, match="authentifiziert oder entschlüsselt"):
        get_or_create_indexed_mapping("project-1", "token", "Token", "secret-token")


def test_windows_key_file_acl_is_restricted_to_current_user(tmp_path, monkeypatch) -> None:
    import os
    import subprocess

    if os.name != "nt":
        pytest.skip("Windows-ACL-Prüfung läuft nur unter Windows.")
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    get_or_create_indexed_mapping("project-1", "host", "Host", "host.internal")
    result = subprocess.run(
        ["icacls", str(mapping_key_path())],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Inherited entries are a failure: the key should have an explicit user ACL.
    assert "(I)" not in result.stdout
    assert "(F)" in result.stdout



def test_windows_mapping_directory_acl_is_restricted(tmp_path, monkeypatch) -> None:
    import os
    import subprocess

    if os.name != "nt":
        pytest.skip("Windows-ACL-Prüfung läuft nur unter Windows.")
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "private-data"))
    get_or_create_indexed_mapping("project-1", "host", "Host", "host.internal")
    directory = mapping_database_path().parent
    result = subprocess.run(
        ["icacls", str(directory)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "(I)" not in result.stdout
    assert "(OI)(CI)(F)" in result.stdout
