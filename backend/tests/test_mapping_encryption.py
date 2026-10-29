from __future__ import annotations

import hashlib
import hmac
import sqlite3
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from logsanitizer.mapping_store import (
    MappingStoreError,
    get_or_create_indexed_mapping,
    mapping_database_path,
    mapping_key_path,
)

KEY_CHECK_CONTEXT = b"logsanitizer:mappings:key-check:v1"
ENCRYPTION_CONTEXT = b"logsanitizer:mappings:encryption:v1"


def _legacy_encrypted_database(path: Path, key: bytes, value: str, *, corrupt: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=None,
        info=b"logsanitizer:mappings:key-derivation:v1",
    ).derive(key)
    encryption_key, lookup_key = derived[:32], derived[32:]
    key_check = hmac.new(lookup_key, KEY_CHECK_CONTEXT, hashlib.sha256).hexdigest()
    ciphertext = b"\x01" + b"\x00" * 12 + AESGCM(encryption_key).encrypt(
        b"\x00" * 12, value.encode(), ENCRYPTION_CONTEXT
    )
    if corrupt:
        ciphertext = ciphertext[:-1] + bytes([ciphertext[-1] ^ 0x01])
    with sqlite3.connect(path) as db:
        db.execute(
            """
            CREATE TABLE indexed_mappings (
                project_id TEXT NOT NULL, category TEXT NOT NULL, prefix TEXT NOT NULL,
                value_hash TEXT NOT NULL, encrypted_value BLOB NOT NULL,
                replacement TEXT NOT NULL, sequence INTEGER NOT NULL,
                PRIMARY KEY (project_id, category, prefix, value_hash),
                UNIQUE (project_id, category, prefix, sequence)
            )
            """
        )
        db.execute(
            "INSERT INTO indexed_mappings VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("project-1", "ip", "IP", "legacy-hash", ciphertext, "[IP_1]", 1),
        )
        db.execute("CREATE TABLE mapping_meta (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO mapping_meta VALUES ('key_check', ?)", (key_check,))


def test_plaintext_mapping_is_stable_and_does_not_create_a_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    secret = "10.123.45.67-sensitive-original"

    first = get_or_create_indexed_mapping("project-1", "ip", "IP", secret)
    second = get_or_create_indexed_mapping("project-1", "ip", "IP", secret)
    next_value = get_or_create_indexed_mapping("project-1", "ip", "IP", "10.123.45.68")

    assert first == second == "[IP_1]"
    assert next_value == "[IP_2]"
    assert not mapping_key_path().exists()
    with sqlite3.connect(mapping_database_path()) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(indexed_mappings)")}
        assert "original_value" in columns
        assert "encrypted_value" not in columns
    assert secret.encode() in mapping_database_path().read_bytes()


def test_same_value_gets_separate_mapping_in_another_project(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    assert get_or_create_indexed_mapping("project-1", "ip", "IP", "192.0.2.1") == "[IP_1]"
    assert get_or_create_indexed_mapping("project-2", "ip", "IP", "192.0.2.1") == "[IP_1]"
    assert get_or_create_indexed_mapping("project-1", "ip", "IP", "192.0.2.2") == "[IP_2]"


def test_legacy_plaintext_database_keeps_existing_replacements(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    path = mapping_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute(
            """
            CREATE TABLE indexed_mappings (
                project_id TEXT NOT NULL, category TEXT NOT NULL, prefix TEXT NOT NULL,
                original_value TEXT NOT NULL, replacement TEXT NOT NULL, sequence INTEGER NOT NULL,
                PRIMARY KEY (project_id, category, prefix, original_value),
                UNIQUE (project_id, category, prefix, sequence)
            )
            """
        )
        db.execute(
            "INSERT INTO indexed_mappings VALUES (?, ?, ?, ?, ?, ?)",
            ("project-1", "ip", "IP", "legacy-value", "[IP_4]", 4),
        )
    assert get_or_create_indexed_mapping("project-1", "ip", "IP", "legacy-value") == "[IP_4]"
    assert get_or_create_indexed_mapping("project-1", "ip", "IP", "new-value") == "[IP_5]"


def test_encrypted_legacy_database_is_migrated_and_key_removed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    key = b"k" * 32
    path = mapping_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    mapping_key_path().write_bytes(key)
    _legacy_encrypted_database(path, key, "old-encrypted-value")

    assert get_or_create_indexed_mapping("project-1", "ip", "IP", "old-encrypted-value") == "[IP_1]"
    assert get_or_create_indexed_mapping("project-1", "ip", "IP", "new-value") == "[IP_2]"
    assert not mapping_key_path().exists()
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(indexed_mappings)")}
        assert "original_value" in columns
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='mapping_meta'").fetchone()[0] == 0
    assert b"old-encrypted-value" in path.read_bytes()


def test_encrypted_legacy_database_without_key_is_preserved(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    path = mapping_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _legacy_encrypted_database(path, b"k" * 32, "cannot-decrypt")
    before = path.read_bytes()

    with pytest.raises(MappingStoreError, match="mappings.key"):
        get_or_create_indexed_mapping("project-1", "ip", "IP", "cannot-decrypt")
    assert path.read_bytes() == before


def test_encrypted_legacy_database_with_corrupt_ciphertext_is_not_migrated(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    path = mapping_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    mapping_key_path().write_bytes(b"k" * 32)
    _legacy_encrypted_database(path, b"k" * 32, "corrupted", corrupt=True)

    with pytest.raises(MappingStoreError, match="nicht entschlüsselt"):
        get_or_create_indexed_mapping("project-1", "ip", "IP", "corrupted")
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(indexed_mappings)")}
        assert "encrypted_value" in columns
    assert mapping_key_path().exists()
