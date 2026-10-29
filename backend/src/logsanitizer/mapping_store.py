"""Project-scoped indexed mappings in a simple local SQLite database.

The current schema stores original values directly in SQLite. Encrypted databases
created by earlier versions are migrated once, preserving their existing mappings.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

DEFAULT_DATA_DIR = ".logsanitizer"
KEY_FILE_NAME = "mappings.key"
_KEY_CHECK_CONTEXT = b"logsanitizer:mappings:key-check:v1"
_ENCRYPTION_CONTEXT = b"logsanitizer:mappings:encryption:v1"


class MappingStoreError(RuntimeError):
    """Mapping data cannot be read or migrated without losing existing mappings."""


# Compatibility name for callers from the encrypted-storage implementation.
MappingEncryptionError = MappingStoreError


def mapping_database_path() -> Path:
    configured = os.environ.get("LOGSANITIZER_MAPPINGS_DIR")
    if configured:
        directory = Path(configured).expanduser()
    else:
        data_dir = os.environ.get("LOGSANITIZER_DATA_DIR")
        directory = Path(data_dir).expanduser() if data_dir else Path.home() / DEFAULT_DATA_DIR
    return directory / "mappings.sqlite3"


def mapping_key_path() -> Path:
    """Return the legacy key path, used only while migrating older encrypted databases."""
    return mapping_database_path().with_name(KEY_FILE_NAME)


def _columns(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(indexed_mappings)").fetchall()
    }


def _create_plaintext_schema(connection: sqlite3.Connection, table: str = "indexed_mappings") -> None:
    connection.execute(
        f"""
        CREATE TABLE {table} (
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


def _legacy_keys(master_key: bytes) -> tuple[bytes, bytes]:
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=None,
        info=b"logsanitizer:mappings:key-derivation:v1",
    ).derive(master_key)
    return derived[:32], derived[32:]


def _legacy_key_check(lookup_key: bytes) -> str:
    return hmac.new(lookup_key, _KEY_CHECK_CONTEXT, hashlib.sha256).hexdigest()


def _decrypt_legacy_value(encryption_key: bytes, ciphertext: bytes) -> str:
    if len(ciphertext) < 29 or ciphertext[0] != 1:
        raise MappingStoreError("Ein alter Mapping-Eintrag hat ein ungültiges Format.")
    try:
        value = AESGCM(encryption_key).decrypt(
            ciphertext[1:13], ciphertext[13:], _ENCRYPTION_CONTEXT
        )
        return value.decode("utf-8")
    except (InvalidTag, ValueError, UnicodeDecodeError) as exc:
        raise MappingStoreError(
            "Bestehende Mapping-Daten konnten nicht entschlüsselt werden. "
            "Datenbank und ursprüngliche Schlüsseldatei werden benötigt."
        ) from exc


def _migrate_encrypted_database(connection: sqlite3.Connection, path: Path) -> None:
    key_path = path.with_name(KEY_FILE_NAME)
    if not key_path.is_file() or key_path.is_symlink():
        raise MappingStoreError(
            "Die alte Mapping-Datenbank benötigt ihre mappings.key-Datei für die einmalige Migration."
        )
    master_key = key_path.read_bytes()
    if len(master_key) != 32:
        raise MappingStoreError("Die alte Mapping-Schlüsseldatei hat ein ungültiges Format.")
    encryption_key, lookup_key = _legacy_keys(master_key)

    meta_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mapping_meta'"
    ).fetchone()
    if not meta_exists:
        raise MappingStoreError("Verschlüsselungsmetadaten fehlen; Migration wurde abgebrochen.")
    check = connection.execute(
        "SELECT value FROM mapping_meta WHERE name='key_check'"
    ).fetchone()
    if check is None or not hmac.compare_digest(str(check[0]), _legacy_key_check(lookup_key)):
        raise MappingStoreError(
            "Die Mapping-Schlüsseldatei passt nicht zur Datenbank; Migration wurde abgebrochen."
        )

    rows = connection.execute(
        """
        SELECT project_id, category, prefix, encrypted_value, replacement, sequence
        FROM indexed_mappings
        ORDER BY project_id, category, prefix, sequence
        """
    ).fetchall()

    connection.execute("ALTER TABLE indexed_mappings RENAME TO indexed_mappings_legacy")
    _create_plaintext_schema(connection)
    for row in rows:
        original_value = _decrypt_legacy_value(encryption_key, bytes(row["encrypted_value"]))
        connection.execute(
            """
            INSERT INTO indexed_mappings
                (project_id, category, prefix, original_value, replacement, sequence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["project_id"], row["category"], row["prefix"], original_value,
                row["replacement"], row["sequence"],
            ),
        )
    connection.execute("DROP TABLE indexed_mappings_legacy")
    connection.execute("DROP TABLE mapping_meta")


def _initialize_schema(connection: sqlite3.Connection, path: Path) -> bool:
    columns = _columns(connection)
    if not columns:
        _create_plaintext_schema(connection)
        return False
    if {"project_id", "category", "prefix", "original_value", "replacement", "sequence"}.issubset(columns):
        return False
    if {"value_hash", "encrypted_value", "replacement", "sequence"}.issubset(columns):
        _migrate_encrypted_database(connection, path)
        return True
    raise MappingStoreError("Unbekanntes Mapping-Datenbankschema; vorhandene Daten bleiben unverändert.")


def get_or_create_indexed_mapping(
    project_id: str, category: str, prefix: str, original_value: str
) -> str:
    """Return the same indexed placeholder for a value throughout one project."""
    path = mapping_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    migrated = False
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("BEGIN IMMEDIATE")
        migrated = _initialize_schema(connection, path)

        row = connection.execute(
            """
            SELECT replacement FROM indexed_mappings
            WHERE project_id = ? AND category = ? AND prefix = ? AND original_value = ?
            """,
            (project_id, category, prefix, original_value),
        ).fetchone()
        if row is not None:
            replacement = str(row["replacement"])
            connection.commit()
            if migrated:
                try:
                    mapping_key_path().unlink(missing_ok=True)
                except OSError:
                    pass
            return replacement

        sequence = int(connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1 FROM indexed_mappings
            WHERE project_id = ? AND category = ? AND prefix = ?
            """,
            (project_id, category, prefix),
        ).fetchone()[0])
        replacement = f"[{prefix}_{sequence}]"
        connection.execute(
            """
            INSERT INTO indexed_mappings
                (project_id, category, prefix, original_value, replacement, sequence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, category, prefix, original_value, replacement, sequence),
        )
        connection.commit()
        if migrated:
            try:
                mapping_key_path().unlink(missing_ok=True)
            except OSError:
                pass
        return replacement
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
