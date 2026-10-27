"""SQLite persistence for local project and imported-file metadata.

Original log contents are never copied into this database. Sensitive mappings
must live in separate, purpose-specific storage.
"""
from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

APP_DIR_NAME = ".logsanitizer"
SCHEMA_VERSION = 2


def database_path() -> Path:
    """Return the configured local database path."""
    configured = os.environ.get("LOGSANITIZER_DATA_DIR")
    data_dir = Path(configured).expanduser() if configured else Path.home() / APP_DIR_NAME
    return data_dir / "logsanitizer.sqlite3"


@contextmanager
def connect_database() -> Iterator[sqlite3.Connection]:
    """Open one short-lived connection and always close it."""
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        # Windows and some filesystems do not support POSIX permission bits.
        pass

    connection = sqlite3.connect(path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    """Create or migrate the metadata schema without touching log files."""
    with connect_database() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_metadata (
                version INTEGER NOT NULL
            )
            """
        )
        row = connection.execute("SELECT version FROM schema_metadata LIMIT 1").fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO schema_metadata (version) VALUES (1)"
            )
            current_version = 1
        else:
            current_version = row["version"]

        if current_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {current_version} is newer than supported "
                f"version {SCHEMA_VERSION}."
            )
        if current_version < 1:
            raise RuntimeError(f"Unsupported database schema version {current_version}.")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'active', 'archived')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at DESC)"
        )

        if current_version < 2:
            connection.execute(
                """
                CREATE TABLE imported_files (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    source_path TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                    modified_at TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    UNIQUE (project_id, source_path)
                )
                """
            )
            connection.execute(
                "CREATE INDEX idx_imported_files_project "
                "ON imported_files(project_id, imported_at)"
            )
            connection.execute(
                "UPDATE schema_metadata SET version = ?", (SCHEMA_VERSION,)
            )


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Projektname darf nicht leer sein.")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()


class Project(BaseModel):
    id: str
    name: str
    description: str
    status: str
    created_at: str
    updated_at: str


class FileImportRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)

    @field_validator("path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Dateipfad darf nicht leer sein.")
        return value


class ImportedFile(BaseModel):
    id: str
    project_id: str
    display_name: str
    size_bytes: int
    modified_at: str
    imported_at: str
    state: str = "registered"
    format_hint: str = "unknown"


def format_hint_for_name(name: str) -> str:
    """Suggest a format from the extension only; never inspect file contents."""
    suffix = Path(name).suffix.casefold()
    if suffix in {".jsonl", ".ndjson"}:
        return "jsonl"
    if suffix == ".json":
        return "json"
    if suffix in {".log", ".txt", ".out", ".err"}:
        return "text"
    if suffix == ".xml":
        return "xml"
    if suffix == ".csv":
        return "csv"
    return "unknown"


class FolderImportRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    recursive: bool = True

    @field_validator("path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Ordnerpfad darf nicht leer sein.")
        return value


class FolderImportIssue(BaseModel):
    file_name: str
    reason: str


class FolderImportResult(BaseModel):
    registered_count: int
    skipped_count: int
    registered_files: list[ImportedFile]
    issues: list[FolderImportIssue]
    limit_reached: bool = False


def _project_from_row(row: sqlite3.Row) -> Project:
    return Project(**dict(row))


def list_projects() -> list[Project]:
    with connect_database() as connection:
        rows = connection.execute(
            """
            SELECT id, name, description, status, created_at, updated_at
            FROM projects ORDER BY updated_at DESC, name COLLATE NOCASE ASC
            """
        ).fetchall()
    return [_project_from_row(row) for row in rows]


def get_project(project_id: str) -> Project | None:
    with connect_database() as connection:
        row = connection.execute(
            """
            SELECT id, name, description, status, created_at, updated_at
            FROM projects WHERE id = ?
            """,
            (project_id,),
        ).fetchone()
    return _project_from_row(row) if row is not None else None


def create_project(payload: ProjectCreate) -> Project:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    project_id = str(uuid4())
    with connect_database() as connection:
        connection.execute(
            """
            INSERT INTO projects (id, name, description, status, created_at, updated_at)
            VALUES (?, ?, ?, 'draft', ?, ?)
            """,
            (project_id, payload.name, payload.description, now, now),
        )
        row = connection.execute(
            """
            SELECT id, name, description, status, created_at, updated_at
            FROM projects WHERE id = ?
            """,
            (project_id,),
        ).fetchone()
    assert row is not None
    return _project_from_row(row)


def _imported_file_from_row(row: sqlite3.Row) -> ImportedFile:
    values = dict(row)
    values["format_hint"] = format_hint_for_name(values["display_name"])
    return ImportedFile(**values)


def list_imported_files(project_id: str) -> list[ImportedFile]:
    with connect_database() as connection:
        rows = connection.execute(
            """
            SELECT id, project_id, display_name, size_bytes, modified_at, imported_at
            FROM imported_files WHERE project_id = ?
            ORDER BY imported_at ASC, display_name COLLATE NOCASE ASC
            """,
            (project_id,),
        ).fetchall()
    return [_imported_file_from_row(row) for row in rows]


def register_imported_file(project_id: str, source: Path) -> ImportedFile:
    """Register a local regular file without opening or modifying its contents."""
    absolute_path = str(source)
    stat = source.stat()
    imported_at = datetime.now(UTC).isoformat(timespec="seconds")
    file_id = str(uuid4())
    with connect_database() as connection:
        existing = connection.execute(
            "SELECT id, project_id, display_name, size_bytes, modified_at, imported_at "
            "FROM imported_files WHERE project_id = ? AND source_path = ?",
            (project_id, absolute_path),
        ).fetchone()
        if existing is not None:
            raise FileAlreadyRegisteredError
        connection.execute(
            """
            INSERT INTO imported_files
                (id, project_id, source_path, display_name, size_bytes, modified_at, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                project_id,
                absolute_path,
                source.name,
                stat.st_size,
                datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(timespec="seconds"),
                imported_at,
            ),
        )
        row = connection.execute(
            """
            SELECT id, project_id, display_name, size_bytes, modified_at, imported_at
            FROM imported_files WHERE id = ?
            """,
            (file_id,),
        ).fetchone()
    assert row is not None
    return _imported_file_from_row(row)


class FileAlreadyRegisteredError(Exception):
    """Raised when the same canonical source path is already in the project."""
