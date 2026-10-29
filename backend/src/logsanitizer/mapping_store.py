"""Project-scoped indexed mappings in a local SQLite database."""
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


def _initialize_schema(connection: sqlite3.Connection) -> None:
    columns = _columns(connection)
    if not columns:
        _create_plaintext_schema(connection)
        return
    required = {
        "project_id", "category", "prefix", "original_value", "replacement", "sequence"
    }
    if required.issubset(columns):
        return
    raise RuntimeError(
        "Unbekanntes Mapping-Datenbankschema. Für die finale Produktversion "
        "muss eine neue Mapping-Datenbank angelegt werden."
    )


def get_or_create_indexed_mapping(
    project_id: str, category: str, prefix: str, original_value: str
) -> str:
    """Return the same indexed placeholder for a value throughout one project."""
    path = mapping_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("BEGIN IMMEDIATE")
        _initialize_schema(connection)

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
        return replacement
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
