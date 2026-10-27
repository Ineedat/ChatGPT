"""Project-scoped indexed replacement mappings stored separately from metadata."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DATA_DIR = ".logsanitizer"


def mapping_database_path() -> Path:
    configured = os.environ.get("LOGSANITIZER_MAPPINGS_DIR")
    if configured:
        directory = Path(configured).expanduser()
    else:
        data_dir = os.environ.get("LOGSANITIZER_DATA_DIR")
        directory = Path(data_dir).expanduser() if data_dir else Path.home() / DEFAULT_DATA_DIR
    return directory / "mappings.sqlite3"


def get_or_create_indexed_mapping(
    project_id: str, category: str, prefix: str, original_value: str
) -> str:
    """Return a stable placeholder for this value within one project and category."""
    path = mapping_database_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass

    connection = sqlite3.connect(path, timeout=10.0)
    try:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS indexed_mappings (
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
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT replacement FROM indexed_mappings
            WHERE project_id = ? AND category = ? AND prefix = ? AND original_value = ?
            """,
            (project_id, category, prefix, original_value),
        ).fetchone()
        if row is not None:
            connection.commit()
            return str(row[0])

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
                (project_id, category, prefix, original_value, replacement, sequence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, category, prefix, original_value, replacement, sequence),
        )
        connection.commit()
        return replacement
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
