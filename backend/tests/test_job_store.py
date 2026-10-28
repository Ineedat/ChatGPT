from __future__ import annotations

import sqlite3

from logsanitizer.job_store import create_job, get_job, initialize_job_database, update_job


def test_job_state_is_persisted_and_paths_are_not_exposed(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    initialize_job_database()
    source = tmp_path / "source.log"
    output = tmp_path / "clean.log"
    source.write_text("source", encoding="utf-8")
    job = create_job("job-1", "project-1", "file-1", source, output, 6)

    update_job("job-1", status="running", phase="sanitizing", processed_bytes=3, lines_processed=1)
    update_job("job-1", status="completed", phase="completed", result={"status": "completed"})

    restored = get_job("job-1")
    assert restored is not None
    assert restored["status"] == "completed"
    assert restored["result"] == {"status": "completed"}
    assert "source_path" not in restored
    assert "output_path" not in restored

    db = sqlite3.connect(tmp_path / "data" / "sanitize_jobs.sqlite3")
    row = db.execute("SELECT source_path, output_path FROM sanitize_jobs WHERE id='job-1'").fetchone()
    db.close()
    assert row == (str(source), str(output))


def test_startup_marks_dead_worker_interrupted_and_cleans_its_staging_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    initialize_job_database()
    source = tmp_path / "source.log"
    output = tmp_path / "clean.log"
    source.write_text("source", encoding="utf-8")
    create_job("stale-job", "project-1", "file-1", source, output, 6)

    staging = tmp_path / ".clean.log.logsanitizer-deadbeef.tmp"
    staging.write_text("partial sanitized data", encoding="utf-8")
    with sqlite3.connect(tmp_path / "data" / "sanitize_jobs.sqlite3") as db:
        db.execute(
            "UPDATE sanitize_jobs SET status='running', phase='sanitizing', process_id=? WHERE id=?",
            (999999999, "stale-job"),
        )

    recovered = initialize_job_database()
    assert recovered == 1
    job = get_job("stale-job")
    assert job is not None
    assert job["status"] == "interrupted"
    assert job["phase"] == "interrupted"
    assert not staging.exists()


def test_startup_preserves_job_owned_by_live_process(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    initialize_job_database()
    source = tmp_path / "source.log"
    output = tmp_path / "clean.log"
    source.write_text("source", encoding="utf-8")
    create_job("live-job", "project-1", "file-1", source, output, 6)

    recovered = initialize_job_database()
    assert recovered == 0
    assert get_job("live-job")["status"] == "queued"


def test_job_store_rejects_unknown_update_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    initialize_job_database()
    source = tmp_path / "source.log"
    output = tmp_path / "clean.log"
    source.write_text("source", encoding="utf-8")
    create_job("job-1", "project-1", "file-1", source, output, 6)

    try:
        update_job("job-1", output_path="/different/path")
    except ValueError as exc:
        assert "Unsupported job fields" in str(exc)
    else:
        raise AssertionError("unknown fields must be rejected")
