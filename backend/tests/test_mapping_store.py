from __future__ import annotations

import sqlite3

from logsanitizer.mapping_store import get_or_create_indexed_mapping, mapping_database_path


def test_indexed_mapping_is_stable_and_project_scoped(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path))
    original_value = "10.123.45.67-sensitive-original"

    first = get_or_create_indexed_mapping("project-1", "ip", "IP", original_value)
    second = get_or_create_indexed_mapping("project-1", "ip", "IP", original_value)
    next_value = get_or_create_indexed_mapping("project-1", "ip", "IP", "10.123.45.68")

    assert first == second == "[IP_1]"
    assert next_value == "[IP_2]"
    assert get_or_create_indexed_mapping("project-2", "ip", "IP", original_value) == "[IP_1]"
    with sqlite3.connect(mapping_database_path()) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(indexed_mappings)")}
        assert "original_value" in columns


def test_existing_mapping_schema_preserves_replacements(tmp_path, monkeypatch) -> None:
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
            ("project-1", "ip", "IP", "existing-value", "[IP_4]", 4),
        )

    assert get_or_create_indexed_mapping("project-1", "ip", "IP", "existing-value") == "[IP_4]"
    assert get_or_create_indexed_mapping("project-1", "ip", "IP", "new-value") == "[IP_5]"
