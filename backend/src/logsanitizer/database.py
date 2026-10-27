"""SQLite persistence for local project metadata.

This module stores metadata only; imported log contents and sensitive mappings
must live in separate, purpose-specific storage.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Iterator
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

APP_DIR_NAME = ".logsanitizer"
SCHEMA_VERSION = 1


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
    """Create the initial schema, without touching any log files."""
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
                "INSERT INTO schema_metadata (version) VALUES (?)", (SCHEMA_VERSION,)
            )
        elif row["version"] != SCHEMA_VERSION:
            raise RuntimeError(
                f"Unsupported database schema version {row['version']}; "
                f"this application supports {SCHEMA_VERSION}."
            )
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
