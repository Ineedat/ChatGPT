"""Durable background sanitization job state and crash recovery."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
ACTIVE = {"queued", "running", "cancelling"}
_RECOVERED_JOB_IDS: list[str] = []


def _directory() -> Path:
    configured = os.environ.get("LOGSANITIZER_DATA_DIR")
    path = Path(configured).expanduser() if configured else Path.home() / ".logsanitizer"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


@contextmanager
def _db():
    path = _directory() / "sanitize_jobs.sqlite3"
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
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


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _pid_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def initialize_job_database() -> int:
    """Create the job ledger, recover stale runs, and remove their staging files."""
    with _db() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""
            CREATE TABLE IF NOT EXISTS sanitize_jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                output_path TEXT NOT NULL,
                status TEXT NOT NULL,
                phase TEXT NOT NULL,
                processed_bytes INTEGER NOT NULL DEFAULT 0,
                total_bytes INTEGER NOT NULL DEFAULT 0,
                lines_processed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                process_id INTEGER NOT NULL,
                error TEXT,
                result_json TEXT
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_sanitize_jobs_project ON sanitize_jobs(project_id, created_at)")
        stale = db.execute(
            "SELECT id, output_path, process_id FROM sanitize_jobs "
            "WHERE status IN ('queued','running','cancelling')"
        ).fetchall()
        recovered = 0
        stale_outputs: set[Path] = set()
        for row in stale:
            if _pid_alive(int(row["process_id"])):
                continue
            stale_outputs.add(Path(row["output_path"]))
            _RECOVERED_JOB_IDS.append(str(row["id"]))
            db.execute(
                "UPDATE sanitize_jobs SET status='interrupted', phase='interrupted', "
                "error='Der Prozess wurde vor Abschluss beendet; bitte den Lauf erneut starten.', "
                "updated_at=? WHERE id=?",
                (_now(), row["id"]),
            )
            recovered += 1
        # Do not touch a same-named staging file while any live job may own that output.
        live_outputs = {
            Path(row["output_path"])
            for row in db.execute(
                "SELECT output_path, process_id FROM sanitize_jobs "
                "WHERE status IN ('queued','running','cancelling')"
            ).fetchall()
            if _pid_alive(int(row["process_id"]))
        }
        for output in stale_outputs - live_outputs:
            try:
                if output.parent.is_dir() and not output.is_symlink():
                    prefix = f".{output.name}.logsanitizer-"
                    for candidate in output.parent.iterdir():
                        if (
                            candidate.name.startswith(prefix)
                            and candidate.name.endswith(".tmp")
                            and candidate.is_file()
                            and not candidate.is_symlink()
                        ):
                            candidate.unlink()
            except OSError:
                # Recovery is fail-safe: keep the durable interrupted status even if cleanup fails.
                pass
        return recovered



def pop_recovered_job_ids() -> list[str]:
    """Return IDs recovered during the most recent initialization pass."""
    recovered = list(dict.fromkeys(_RECOVERED_JOB_IDS))
    _RECOVERED_JOB_IDS.clear()
    return recovered


def create_job(
    job_id: str, project_id: str, file_id: str, source: Path, output: Path, total_bytes: int
) -> dict[str, Any]:
    now = _now()
    job = {
        "id": job_id, "project_id": project_id, "file_id": file_id,
        "status": "queued", "phase": "queued", "processed_bytes": 0,
        "total_bytes": total_bytes, "lines_processed": 0, "created_at": now,
        "updated_at": now,
    }
    with _db() as db:
        db.execute(
            "INSERT INTO sanitize_jobs(id,project_id,file_id,source_path,output_path,status,phase,"
            "processed_bytes,total_bytes,lines_processed,created_at,updated_at,process_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, project_id, file_id, str(source), str(output), "queued", "queued",
             0, total_bytes, 0, now, now, os.getpid()),
        )
    return job


def update_job(job_id: str, **changes: Any) -> dict[str, Any] | None:
    allowed = {"status", "phase", "processed_bytes", "total_bytes", "lines_processed", "error", "result"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"Unsupported job fields: {', '.join(sorted(unknown))}")
    values = dict(changes)
    result = values.pop("result", None)
    if result is not None:
        values["result_json"] = json.dumps(result, ensure_ascii=False)
    values["updated_at"] = _now()
    assignments = ", ".join(f"{key}=?" for key in values)
    with _db() as db:
        cursor = db.execute(
            f"UPDATE sanitize_jobs SET {assignments} WHERE id=?",
            (*values.values(), job_id),
        )
        if cursor.rowcount == 0:
            return None
        row = db.execute("SELECT * FROM sanitize_jobs WHERE id=?", (job_id,)).fetchone()
        return _public_row(row)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _db() as db:
        row = db.execute("SELECT * FROM sanitize_jobs WHERE id=?", (job_id,)).fetchone()
        return _public_row(row) if row else None


def _public_row(row: sqlite3.Row) -> dict[str, Any]:
    result = {
        "id": row["id"], "project_id": row["project_id"], "file_id": row["file_id"],
        "status": row["status"], "phase": row["phase"],
        "processed_bytes": row["processed_bytes"], "total_bytes": row["total_bytes"],
        "lines_processed": row["lines_processed"], "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row["error"]:
        result["error"] = row["error"]
    if row["result_json"]:
        result["result"] = json.loads(row["result_json"])
    return result
