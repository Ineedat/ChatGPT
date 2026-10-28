"""Project-scoped indexed mappings encrypted at rest with a separate local key file."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

DEFAULT_DATA_DIR = ".logsanitizer"
KEY_FILE_NAME = "mappings.key"
KEY_BYTES = 32
FORMAT_VERSION = 1
_KEY_CHECK_CONTEXT = b"logsanitizer:mappings:key-check:v1"
_LOOKUP_CONTEXT = b"logsanitizer:mappings:lookup:v1"
_ENCRYPTION_CONTEXT = b"logsanitizer:mappings:encryption:v1"


class MappingEncryptionError(RuntimeError):
    """Raised when mapping encryption cannot safely be initialized or used."""


def mapping_database_path() -> Path:
    configured = os.environ.get("LOGSANITIZER_MAPPINGS_DIR")
    if configured:
        directory = Path(configured).expanduser()
    else:
        data_dir = os.environ.get("LOGSANITIZER_DATA_DIR")
        directory = Path(data_dir).expanduser() if data_dir else Path.home() / DEFAULT_DATA_DIR
    return directory / "mappings.sqlite3"


def mapping_key_path() -> Path:
    return mapping_database_path().with_name(KEY_FILE_NAME)


def _restrict_key_file(path: Path) -> None:
    """Restrict key-file access on supported platforms; fail closed on Windows ACL errors."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        if os.name != "nt":
            raise MappingEncryptionError("Schlüsseldatei-Berechtigungen konnten nicht gesetzt werden.")
    if os.name == "nt":
        domain = os.environ.get("USERDOMAIN")
        username = os.environ.get("USERNAME")
        identity = f"{domain}\\{username}" if domain and username else username
        if not identity:
            raise MappingEncryptionError("Windows-Benutzer konnte für die Schlüsselrechte nicht ermittelt werden.")
        try:
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{identity}:(F)"],
                check=True,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise MappingEncryptionError(
                "Zugriffsrechte der Schlüsseldatei konnten unter Windows nicht eingeschränkt werden."
            ) from exc


def _load_or_create_key(path: Path, encrypted_schema_exists: bool) -> bytes:
    key_path = path.with_name(KEY_FILE_NAME)
    if key_path.exists():
        if key_path.is_symlink() or not key_path.is_file():
            raise MappingEncryptionError("Die Mapping-Schlüsseldatei ist kein regulärer lokaler Datei-Eintrag.")
        _restrict_key_file(key_path)
        key = key_path.read_bytes()
        if len(key) != KEY_BYTES:
            raise MappingEncryptionError("Die Mapping-Schlüsseldatei hat ein ungültiges Format.")
        return key
    if encrypted_schema_exists:
        raise MappingEncryptionError(
            "Die Mapping-Schlüsseldatei fehlt. Es werden keine neuen Schlüssel erzeugt, "
            "da bestehende Zuordnungen sonst nicht mehr zuverlässig nutzbar wären."
        )

    key = secrets.token_bytes(KEY_BYTES)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(key_path, flags, 0o600)
        # Set ACLs before writing key material on Windows.
        _restrict_key_file(key_path)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(key)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        # Another local process may have initialized the key concurrently.
        if key_path.is_symlink() or not key_path.is_file():
            raise MappingEncryptionError("Die Mapping-Schlüsseldatei ist kein regulärer Datei-Eintrag.")
        _restrict_key_file(key_path)
        key = key_path.read_bytes()
        if len(key) != KEY_BYTES:
            raise MappingEncryptionError("Die Mapping-Schlüsseldatei hat ein ungültiges Format.")
    except Exception:
        try:
            key_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return key


def _derive_keys(master_key: bytes) -> tuple[bytes, bytes]:
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=None,
        info=b"logsanitizer:mappings:key-derivation:v1",
    ).derive(master_key)
    return derived[:32], derived[32:]


def _key_check(lookup_key: bytes) -> str:
    return hmac.new(lookup_key, _KEY_CHECK_CONTEXT, hashlib.sha256).hexdigest()


def _value_hash(lookup_key: bytes, original_value: str) -> str:
    return hmac.new(
        lookup_key,
        _LOOKUP_CONTEXT + original_value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _encrypt_value(encryption_key: bytes, original_value: str) -> bytes:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(encryption_key).encrypt(
        nonce,
        original_value.encode("utf-8"),
        _ENCRYPTION_CONTEXT,
    )
    return bytes([FORMAT_VERSION]) + nonce + ciphertext


def _decrypt_value(encryption_key: bytes, ciphertext: bytes) -> str:
    if len(ciphertext) < 1 + 12 + 16 or ciphertext[0] != FORMAT_VERSION:
        raise MappingEncryptionError("Ein verschlüsselter Mapping-Eintrag hat ein ungültiges Format.")
    try:
        plaintext = AESGCM(encryption_key).decrypt(
            ciphertext[1:13],
            ciphertext[13:],
            _ENCRYPTION_CONTEXT,
        )
        return plaintext.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise MappingEncryptionError(
            "Mapping-Daten konnten nicht authentifiziert oder entschlüsselt werden."
        ) from exc


def _columns(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(indexed_mappings)").fetchall()
    }


def _initialize_encrypted_schema(
    connection: sqlite3.Connection, encryption_key: bytes, lookup_key: bytes
) -> None:
    columns = _columns(connection)
    if not columns:
        connection.execute(
            """
            CREATE TABLE indexed_mappings (
                project_id TEXT NOT NULL,
                category TEXT NOT NULL,
                prefix TEXT NOT NULL,
                value_hash TEXT NOT NULL,
                encrypted_value BLOB NOT NULL,
                replacement TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK (sequence > 0),
                PRIMARY KEY (project_id, category, prefix, value_hash),
                UNIQUE (project_id, category, prefix, sequence)
            )
            """
        )
    elif "original_value" in columns and "value_hash" not in columns:
        # One-time in-place migration from the previous plaintext schema.
        rows = connection.execute(
            "SELECT project_id, category, prefix, original_value, replacement, sequence "
            "FROM indexed_mappings"
        ).fetchall()
        connection.execute("PRAGMA secure_delete=ON")
        connection.execute("ALTER TABLE indexed_mappings RENAME TO indexed_mappings_plaintext_migration")
        connection.execute(
            """
            CREATE TABLE indexed_mappings (
                project_id TEXT NOT NULL,
                category TEXT NOT NULL,
                prefix TEXT NOT NULL,
                value_hash TEXT NOT NULL,
                encrypted_value BLOB NOT NULL,
                replacement TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK (sequence > 0),
                PRIMARY KEY (project_id, category, prefix, value_hash),
                UNIQUE (project_id, category, prefix, sequence)
            )
            """
        )
        for row in rows:
            original_value = str(row["original_value"])
            connection.execute(
                """
                INSERT INTO indexed_mappings
                    (project_id, category, prefix, value_hash, encrypted_value, replacement, sequence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["project_id"], row["category"], row["prefix"],
                    _value_hash(lookup_key, original_value),
                    _encrypt_value(encryption_key, original_value),
                    row["replacement"], row["sequence"],
                ),
            )
        connection.execute("DROP TABLE indexed_mappings_plaintext_migration")
        # Rebuild the database file to avoid retaining dropped plaintext pages where SQLite permits.
        connection.execute("VACUUM")
    elif not {"value_hash", "encrypted_value"}.issubset(columns):
        raise MappingEncryptionError("Unbekanntes Mapping-Datenbankschema; Start wird sicherheitshalber abgebrochen.")

    connection.execute(
        "CREATE TABLE IF NOT EXISTS mapping_meta (name TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    expected = _key_check(lookup_key)
    existing = connection.execute(
        "SELECT value FROM mapping_meta WHERE name='key_check'"
    ).fetchone()
    if existing is None:
        if connection.execute("SELECT COUNT(*) FROM indexed_mappings").fetchone()[0]:
            raise MappingEncryptionError(
                "Verschlüsselungsmetadaten fehlen bei vorhandenen Mapping-Einträgen; "
                "die Datenbank wird nicht automatisch verändert."
            )
        connection.execute(
            "INSERT INTO mapping_meta(name, value) VALUES('key_check', ?)", (expected,)
        )
    elif not hmac.compare_digest(str(existing[0]), expected):
        raise MappingEncryptionError(
            "Die Mapping-Schlüsseldatei passt nicht zu dieser Datenbank. "
            "Datenbank und Schlüssel dürfen nicht unabhängig voneinander ersetzt werden."
        )


def get_or_create_indexed_mapping(
    project_id: str, category: str, prefix: str, original_value: str
) -> str:
    """Return a stable project-scoped placeholder without storing source values in plaintext."""
    path = mapping_database_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        if os.name != "nt":
            raise MappingEncryptionError("Verzeichnisrechte für Mapping-Daten konnten nicht gesetzt werden.")

    connection = sqlite3.connect(path, timeout=10.0)
    connection.row_factory = sqlite3.Row
    try:
        try:
            os.chmod(path, 0o600)
        except OSError:
            if os.name != "nt":
                raise MappingEncryptionError("Dateirechte der Mapping-Datenbank konnten nicht gesetzt werden.")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA secure_delete = ON")
        columns = _columns(connection)
        encrypted_schema_exists = "value_hash" in columns and "encrypted_value" in columns
        master_key = _load_or_create_key(path, encrypted_schema_exists)
        encryption_key, lookup_key = _derive_keys(master_key)
        connection.execute("BEGIN IMMEDIATE")
        _initialize_encrypted_schema(connection, encryption_key, lookup_key)
        value_hash = _value_hash(lookup_key, original_value)
        row = connection.execute(
            """
            SELECT replacement FROM indexed_mappings
            WHERE project_id = ? AND category = ? AND prefix = ? AND value_hash = ?
            """,
            (project_id, category, prefix, value_hash),
        ).fetchone()
        if row is not None:
            connection.commit()
            return str(row["replacement"])

        sequence_row = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1 FROM indexed_mappings
            WHERE project_id = ? AND category = ? AND prefix = ?
            """,
            (project_id, category, prefix),
        ).fetchone()
        sequence = int(sequence_row[0])
        replacement = f"[{prefix}_{sequence}]"
        connection.execute(
            """
            INSERT INTO indexed_mappings
                (project_id, category, prefix, value_hash, encrypted_value, replacement, sequence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id, category, prefix, value_hash,
                _encrypt_value(encryption_key, original_value), replacement, sequence,
            ),
        )
        connection.commit()
        return replacement
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
