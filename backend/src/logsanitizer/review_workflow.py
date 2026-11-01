"""Persistent review workflow, literal output sampling, and append-only audit events.

Only sanitized output paths are searchable; original source paths and log contents
are never returned by review metadata endpoints.
"""
from __future__ import annotations

import difflib
import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import regex as re
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from logsanitizer.database import connect_database
from logsanitizer.notifications import notify_returned_run

router = APIRouter(prefix="/api/reviews", tags=["review"])
VALID_STATUSES = {
    "queued", "running", "pending_review", "returned", "approved",
    "approved_with_exception", "stopped", "failed", "cancelled",
}
MAX_SEARCH_RESULTS = 20
MAX_LINE_BYTES = 1024 * 1024


def _path() -> Path:
    configured = os.environ.get("LOGSANITIZER_DATA_DIR")
    directory = Path(configured).expanduser() if configured else Path.home() / ".logsanitizer"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    return directory / "review.sqlite3"


@contextmanager
def _db():
    path = _path()
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _file_signature(path: Path) -> str | None:
    """Identify the exact output file created by the successful sanitization run."""
    try:
        if path.is_symlink() or not path.is_file():
            return None
        info = path.stat()
        return f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}"
    except OSError:
        return None


def initialize_review_database() -> None:
    with _db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS review_runs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            file_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            output_name TEXT NOT NULL,
            output_path TEXT NOT NULL,
            publish_path TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK (status IN (
                'queued','running','pending_review','returned','approved',
                'approved_with_exception','stopped','failed','cancelled'
            )),
            actor_user_id INTEGER NOT NULL,
            actor_username TEXT NOT NULL,
            reviewer_user_id INTEGER,
            parent_run_id TEXT REFERENCES review_runs(id),
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            input_bytes INTEGER NOT NULL DEFAULT 0,
            output_bytes INTEGER NOT NULL DEFAULT 0,
            lines_processed INTEGER NOT NULL DEFAULT 0,
            replacements INTEGER NOT NULL DEFAULT 0,
            validated INTEGER NOT NULL DEFAULT 0,
            residual_matches INTEGER NOT NULL DEFAULT 0,
            validation_scope TEXT NOT NULL DEFAULT '',
            output_signature TEXT NOT NULL DEFAULT '',
            last_comment TEXT NOT NULL DEFAULT '',
            exception_reason TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_review_runs_status_created
            ON review_runs(status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_review_runs_project_created
            ON review_runs(project_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS review_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES review_runs(id),
            actor_user_id INTEGER,
            actor_username TEXT NOT NULL,
            action TEXT NOT NULL,
            comment TEXT NOT NULL DEFAULT '',
            exception_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_review_events_run_created
            ON review_events(run_id, created_at DESC);
        CREATE TRIGGER IF NOT EXISTS review_events_no_update
            BEFORE UPDATE ON review_events
            BEGIN SELECT RAISE(ABORT, 'review audit events are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS review_events_no_delete
            BEFORE DELETE ON review_events
            BEGIN SELECT RAISE(ABORT, 'review audit events are immutable'); END;
        CREATE TABLE IF NOT EXISTS saved_searches (
            id TEXT PRIMARY KEY,
            owner_user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            query TEXT NOT NULL,
            match_type TEXT NOT NULL DEFAULT 'literal',
            created_at TEXT NOT NULL,
            UNIQUE(owner_user_id, name)
        );
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(review_runs)")}
        if "publish_path" not in columns:
            db.execute("ALTER TABLE review_runs ADD COLUMN publish_path TEXT NOT NULL DEFAULT ''")
        if "output_signature" not in columns:
            db.execute("ALTER TABLE review_runs ADD COLUMN output_signature TEXT NOT NULL DEFAULT ''")
        saved_columns = {row["name"] for row in db.execute("PRAGMA table_info(saved_searches)")}
        if "match_type" not in saved_columns:
            db.execute("ALTER TABLE saved_searches ADD COLUMN match_type TEXT NOT NULL DEFAULT 'literal'")
    try:
        os.chmod(_path(), 0o600)
    except OSError:
        pass


def _audit(db, run_id: str, actor_id: int | None, actor_name: str,
           action: str, comment: str = "", exception_reason: str = "") -> None:
    db.execute(
        """INSERT INTO review_events
           (run_id, actor_user_id, actor_username, action, comment, exception_reason, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (run_id, actor_id, actor_name, action, comment, exception_reason, _now()),
    )


def _review_assignee_state() -> bool | None:
    """Return whether a reviewer/approver is assigned; None means lookup failed."""
    configured = os.environ.get("LOGSANITIZER_DATA_DIR")
    directory = Path(configured).expanduser() if configured else Path.home() / ".logsanitizer"
    path = directory / "auth.sqlite3"
    if not path.is_file():
        return None
    try:
        with sqlite3.connect(path, timeout=3) as db:
            row = db.execute(
                """SELECT 1 FROM users u JOIN user_roles r ON r.user_id=u.id
                   WHERE u.enabled=1 AND r.role IN ('reviewer','approver') LIMIT 1"""
            ).fetchone()
        return row is not None
    except sqlite3.Error:
        return None


def create_run(run_id: str, project_id: str, file_id: str, display_name: str,
               output_path: Path, actor_id: int, actor_name: str,
               parent_run_id: str | None = None,
               publish_path: Path | None = None) -> dict:
    initialize_review_database()
    with _db() as db:
        if parent_run_id:
            parent = db.execute(
                "SELECT project_id, file_id, status FROM review_runs WHERE id=?",
                (parent_run_id,),
            ).fetchone()
            if (parent is None or parent["status"] != "returned"
                    or parent["project_id"] != project_id or parent["file_id"] != file_id):
                raise ValueError("Nur ein zurückgegebener Lauf derselben Datei kann überarbeitet werden.")
        db.execute(
            """INSERT INTO review_runs
               (id, project_id, file_id, display_name, output_name, output_path, publish_path, status,
                actor_user_id, actor_username, parent_run_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
            (run_id, project_id, file_id, display_name, output_path.name,
             str(output_path), str(publish_path or output_path), actor_id, actor_name,
             parent_run_id, _now()),
        )
        _audit(db, run_id, actor_id, actor_name, "queued",
               comment=f"Überarbeitung von Lauf {parent_run_id}" if parent_run_id else "")
        return _public_run(db.execute("SELECT * FROM review_runs WHERE id=?", (run_id,)).fetchone())


def _publish_approved_output(db: sqlite3.Connection, row: sqlite3.Row) -> str:
    """Move a validated work file into its final output location without overwriting."""
    work_path = Path(row["output_path"])
    publish_value = row["publish_path"]
    publish_path = Path(publish_value) if publish_value else work_path
    if work_path == publish_path:
        signature = _file_signature(work_path)
        if signature is None:
            raise HTTPException(status_code=409, detail="Arbeitsdatei fehlt oder ist nicht mehr verfügbar.")
        return signature
    if work_path.is_symlink() or not work_path.is_file():
        raise HTTPException(status_code=409, detail="Arbeitsdatei fehlt oder ist nicht mehr verfügbar.")
    publish_path.parent.mkdir(parents=True, exist_ok=True)
    if publish_path.exists() or publish_path.is_symlink():
        raise HTTPException(status_code=409, detail="Die Zieldatei existiert bereits; Freigabe wurde nicht veröffentlicht.")

    temporary: Path | None = None
    try:
        try:
            os.link(work_path, publish_path)
        except OSError:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{publish_path.name}.", suffix=".publishing", dir=publish_path.parent
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as target, work_path.open("rb") as source:
                shutil.copyfileobj(source, target, length=1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
            try:
                os.link(temporary, publish_path)
            except OSError:
                if publish_path.exists() or publish_path.is_symlink():
                    raise FileExistsError(publish_path)
                temporary.replace(publish_path)
            temporary.unlink(missing_ok=True)
            temporary = None
        work_path.unlink()
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise HTTPException(
            status_code=409,
            detail="Die bereinigte Datei konnte nicht in den Ausgabeordner übernommen werden.",
        ) from exc

    signature = _file_signature(publish_path)
    if signature is None:
        raise HTTPException(status_code=409, detail="Die veröffentlichte Datei konnte nicht verifiziert werden.")
    db.execute(
        "UPDATE review_runs SET output_path=?, output_signature=? WHERE id=?",
        (str(publish_path), signature, row["id"]),
    )
    return signature


def set_run_running(run_id: str) -> None:
    with _db() as db:
        db.execute(
            "UPDATE review_runs SET status='running', started_at=? WHERE id=? AND status='queued'",
            (_now(), run_id),
        )
        row = db.execute("SELECT actor_user_id, actor_username FROM review_runs WHERE id=?", (run_id,)).fetchone()
        if row:
            _audit(db, run_id, row["actor_user_id"], row["actor_username"], "started")


def finish_run(run_id: str, result: dict[str, object]) -> dict:
    assigned = _review_assignee_state()
    # Fail closed when assignment state cannot be established.
    status = "pending_review" if assigned is not False else "approved"
    with _db() as db:
        row = db.execute("SELECT * FROM review_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("Bereinigungslauf nicht gefunden.")
        signature = _file_signature(Path(row["output_path"]))
        validated = (
            bool(result.get("validated"))
            and int(result.get("residual_matches", 1)) == 0
            and signature is not None
        )
        if not validated:
            status = "failed"
        elif status == "approved":
            try:
                signature = _publish_approved_output(db, row)
            except HTTPException:
                status = "failed"
        db.execute(
            """UPDATE review_runs SET status=?, completed_at=?, input_bytes=?, output_bytes=?,
               lines_processed=?, replacements=?, validated=?, residual_matches=?, validation_scope=?,
               output_signature=? WHERE id=?""",
            (status, _now(), int(result.get("input_bytes", 0)), int(result.get("output_bytes", 0)),
             int(result.get("lines_processed", 0)), int(result.get("replacements", 0)),
             int(validated), int(result.get("residual_matches", 0)),
             str(result.get("validation_scope", "")), signature or "", run_id),
        )
        if status == "approved":
            _audit(db, run_id, None, "system", "auto_approved",
                   comment="Keine aktive Reviewer-/Approver-Zuweisung; Pflichtvalidierung bestanden.")
        elif status == "pending_review":
            _audit(db, run_id, None, "system", "pending_review",
                   comment="Pflichtvalidierung bestanden; bewusste Freigabe erforderlich.")
        else:
            _audit(db, run_id, None, "system", "failed",
                   comment="Pflichtvalidierung fehlgeschlagen oder Ausgabe konnte nicht veröffentlicht werden.")
        return _public_run(db.execute("SELECT * FROM review_runs WHERE id=?", (run_id,)).fetchone())


def fail_run(run_id: str, status: str, comment: str = "") -> None:
    if status not in {"failed", "cancelled"}:
        raise ValueError("Ungültiger Abschlussstatus.")
    with _db() as db:
        row = db.execute("SELECT actor_user_id, actor_username FROM review_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return
        db.execute(
            "UPDATE review_runs SET status=?, completed_at=?, last_comment=? WHERE id=?",
            (status, _now(), comment[:1000], run_id),
        )
        _audit(db, run_id, row["actor_user_id"], row["actor_username"], status, comment=comment[:1000])


def _public_run(row: sqlite3.Row | None) -> dict:
    if row is None:
        raise ValueError("Bereinigungslauf nicht gefunden.")
    return {key: row[key] for key in (
        "id", "project_id", "file_id", "display_name", "output_name", "status",
        "actor_user_id", "actor_username", "reviewer_user_id", "parent_run_id",
        "created_at", "started_at", "completed_at", "input_bytes", "output_bytes",
        "lines_processed", "replacements", "validated", "residual_matches",
        "validation_scope", "last_comment", "exception_reason",
    )} | {"published": row["status"] in {"approved", "approved_with_exception"}}


def is_file_approved(project_id: str, file_id: str) -> bool:
    """Return whether a file has an approved run and is therefore locked from reprocessing."""
    initialize_review_database()
    with _db() as db:
        row = db.execute(
            """SELECT 1 FROM review_runs
               WHERE project_id=? AND file_id=?
                 AND status IN ('approved', 'approved_with_exception')
               LIMIT 1""",
            (project_id, file_id),
        ).fetchone()
    return row is not None


def get_run(run_id: str) -> dict | None:
    initialize_review_database()
    with _db() as db:
        row = db.execute("SELECT * FROM review_runs WHERE id=?", (run_id,)).fetchone()
        return _public_run(row) if row else None


def list_runs(status: str | None = None, limit: int = 100, owner_user_id: int | None = None) -> list[dict]:
    initialize_review_database()
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Ungültiger Laufstatus.")
    with _db() as db:
        clauses = []
        values: list[object] = []
        if status:
            clauses.append("status=?")
            values.append(status)
        if owner_user_id is not None:
            clauses.append("actor_user_id=?")
            values.append(owner_user_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(min(limit, 200))
        rows = db.execute(
            f"SELECT * FROM review_runs{where} ORDER BY created_at DESC, rowid DESC LIMIT ?",
            values,
        ).fetchall()
        return [_public_run(row) for row in rows]


def _actor(request: Request) -> tuple[int, str]:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Anmeldung erforderlich.")
    return int(user["id"]), str(user["username"])


class SavedSearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=200)
    match_type: str = "literal"

    @field_validator("match_type")
    @classmethod
    def validate_match_type(cls, value: str) -> str:
        if value not in {"literal", "regex"}:
            raise ValueError("Suchart muss literal oder regex sein.")
        return value

    @field_validator("name", "query")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Name und Suchbegriff müssen druckbaren Text enthalten.")
        return value


class ReviewDecision(BaseModel):
    comment: str = Field(default="", max_length=1000)
    exception: bool = False
    exception_reason: str = Field(default="", max_length=1000)

    @field_validator("comment", "exception_reason")
    @classmethod
    def normalize_comment(cls, value: str) -> str:
        return value.strip()


class ReviewComment(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Kommentar darf nicht leer sein.")
        return value



MAX_COMPARE_PREVIEW_BYTES = 65_536


def _read_compare_window(path: Path, byte_offset: int) -> dict[str, object]:
    """Read one bounded UTF-8 window without loading the complete log into memory."""
    if path.is_symlink() or not path.is_file():
        raise HTTPException(status_code=410, detail="Datei ist nicht mehr verfügbar.")
    total_bytes = path.stat().st_size
    requested = max(0, min(byte_offset, total_bytes))
    with path.open("rb") as stream:
        stream.seek(requested)
        if requested:
            stream.seek(requested - 1)
            previous_byte = stream.read(1)
            stream.seek(requested)
            if previous_byte != b"\n":
                stream.readline(MAX_LINE_BYTES + 1)
        actual_offset = stream.tell()
        raw = stream.read(MAX_COMPARE_PREVIEW_BYTES + 1)
    if len(raw) > MAX_COMPARE_PREVIEW_BYTES:
        raw = raw[:MAX_COMPARE_PREVIEW_BYTES]
        last_newline = raw.rfind(b"\n")
        if last_newline > 0:
            raw = raw[:last_newline + 1]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Datei enthält an dieser Stelle kein gültiges UTF-8.") from exc
    next_offset = actual_offset + len(raw)
    return {
        "content": text,
        "byte_offset": actual_offset,
        "previous_offset": max(0, actual_offset - MAX_COMPARE_PREVIEW_BYTES) if actual_offset else None,
        "next_offset": next_offset if next_offset < total_bytes else None,
        "total_bytes": total_bytes,
    }


def _changed_line_spans(
    original: str, sanitized: str
) -> tuple[list[int], list[int], list[dict[str, int]], list[dict[str, int]]]:
    """Return line and character spans changed by sanitization for precise highlighting."""
    original_lines = original.splitlines(keepends=True)
    sanitized_lines = sanitized.splitlines(keepends=True)
    original_text = [line.rstrip("\\r\\n") for line in original_lines]
    sanitized_text = [line.rstrip("\\r\\n") for line in sanitized_lines]
    matcher = difflib.SequenceMatcher(a=original_text, b=sanitized_text)
    original_spans: list[dict[str, int]] = []
    sanitized_spans: list[dict[str, int]] = []

    def add_whole_line(target: list[dict[str, int]], line_number: int, value: str) -> None:
        target.append({"line_number": line_number, "start": 0, "end": max(1, len(value))})

    for tag, original_start, original_end, sanitized_start, sanitized_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        paired = min(original_end - original_start, sanitized_end - sanitized_start)
        for offset in range(paired):
            original_line_number = original_start + offset + 1
            sanitized_line_number = sanitized_start + offset + 1
            original_line = original_text[original_start + offset]
            sanitized_line = sanitized_text[sanitized_start + offset]
            if len(original_line) + len(sanitized_line) > 8192:
                add_whole_line(original_spans, original_line_number, original_line)
                add_whole_line(sanitized_spans, sanitized_line_number, sanitized_line)
                continue
            line_matcher = difflib.SequenceMatcher(a=original_line, b=sanitized_line)
            for line_tag, a_start, a_end, b_start, b_end in line_matcher.get_opcodes():
                if line_tag == "equal":
                    continue
                if a_end > a_start:
                    original_spans.append({
                        "line_number": original_line_number, "start": a_start, "end": a_end
                    })
                if b_end > b_start:
                    sanitized_spans.append({
                        "line_number": sanitized_line_number, "start": b_start, "end": b_end
                    })
        for index in range(original_start + paired, original_end):
            add_whole_line(original_spans, index + 1, original_text[index])
        for index in range(sanitized_start + paired, sanitized_end):
            add_whole_line(sanitized_spans, index + 1, sanitized_text[index])

    original_spans.sort(key=lambda item: (item["line_number"], item["start"]))
    sanitized_spans.sort(key=lambda item: (item["line_number"], item["start"]))
    original_changed = sorted({item["line_number"] for item in original_spans})
    sanitized_changed = sorted({item["line_number"] for item in sanitized_spans})
    return original_changed, sanitized_changed, original_spans, sanitized_spans


@router.get("/runs/{run_id}/compare-preview")
def compare_run_preview(
    run_id: str,
    request: Request,
    original_offset: int = Query(default=0, ge=0),
    output_offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    """Show bounded original/output windows for a reviewer, validating output identity."""
    user = getattr(request.state, "user", None)
    if not user or not set(user.get("roles", [])).intersection({"admin", "reviewer", "approver"}):
        raise HTTPException(status_code=403, detail="Keine Berechtigung für den Dateivergleich.")
    initialize_review_database()
    with _db() as db:
        row = db.execute("SELECT * FROM review_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Bereinigungslauf nicht gefunden.")
        if row["status"] in {"queued", "running", "failed", "cancelled", "stopped"}:
            raise HTTPException(status_code=409, detail="Für diesen Lauf liegt keine prüfbare Ausgabe vor.")
        output_path = Path(row["output_path"])
        expected_signature = row["output_signature"]
        project_id, file_id = row["project_id"], row["file_id"]
    with connect_database() as db:
        source_row = db.execute(
            "SELECT source_path FROM imported_files WHERE project_id=? AND id=?",
            (project_id, file_id),
        ).fetchone()
    if source_row is None:
        raise HTTPException(status_code=410, detail="Originaldatei ist nicht mehr registriert.")
    source_path = Path(source_row["source_path"])
    if not expected_signature or _file_signature(output_path) != expected_signature:
        raise HTTPException(status_code=409, detail="Bereinigte Ausgabe fehlt oder wurde seit der Validierung verändert.")
    original = _read_compare_window(source_path, original_offset)
    sanitized = _read_compare_window(output_path, output_offset)
    (
        original_changed,
        sanitized_changed,
        original_spans,
        sanitized_spans,
    ) = _changed_line_spans(str(original["content"]), str(sanitized["content"]))
    return {
        "run_id": run_id,
        "original": original,
        "sanitized": sanitized,
        "original_changed_lines": original_changed,
        "sanitized_changed_lines": sanitized_changed,
        "original_changed_spans": original_spans,
        "sanitized_changed_spans": sanitized_spans,
    }


@router.get("/queue")
def review_queue() -> list[dict]:
    return list_runs(status="pending_review", limit=200)


@router.get("/runs")
def run_history(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict]:
    actor_id, _ = _actor(request)
    roles = set(request.state.user["roles"])
    reviewer_roles = {"admin", "reviewer", "approver"}
    owner_id = None if roles.intersection(reviewer_roles) else actor_id
    return list_runs(status, limit, owner_id)


@router.get("/runs/{run_id}/search")
def search_sanitized_output(
    run_id: str,
    request: Request,
    q: str | None = Query(default=None, min_length=1, max_length=200),
    saved_search_id: str | None = Query(default=None, min_length=1, max_length=80),
    match_type: str = Query(default="literal"),
) -> dict:
    actor_id, _ = _actor(request)
    if bool(q) == bool(saved_search_id):
        raise HTTPException(status_code=422, detail="Genau ein Suchbegriff oder gespeichertes Suchmuster angeben.")
    initialize_review_database()
    with _db() as db:
        row = db.execute("SELECT * FROM review_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Bereinigungslauf nicht gefunden.")
        if row["status"] != "pending_review":
            raise HTTPException(status_code=409, detail="Nur ausstehende Läufe können geprüft werden.")
        if saved_search_id:
            saved = db.execute(
                "SELECT query, match_type FROM saved_searches WHERE id=? AND owner_user_id=?",
                (saved_search_id, actor_id),
            ).fetchone()
            if saved is None:
                raise HTTPException(status_code=404, detail="Gespeichertes Suchmuster nicht gefunden.")
            query = str(saved["query"])
            match_type = str(saved["match_type"])
        else:
            query = str(q).strip()
        if not query or len(query) > 200 or any(ord(char) < 32 for char in query):
            raise HTTPException(status_code=422, detail="Ungültiger Suchbegriff.")
        if match_type not in {"literal", "regex"}:
            raise HTTPException(status_code=422, detail="Suchart muss literal oder regex sein.")
        try:
            compiled_query = re.compile(re.escape(query) if match_type == "literal" else query, re.IGNORECASE)
        except re.error as exc:
            raise HTTPException(status_code=422, detail=f"Ungültiger regulärer Ausdruck: {exc}") from exc
        output_path = Path(row["output_path"])
        expected_signature = row["output_signature"]
    if not expected_signature:
        raise HTTPException(status_code=409, detail="Keine validierte Ausgabe für diesen Lauf gespeichert.")
    results = []
    try:
        with output_path.open("rb") as stream:
            info = os.fstat(stream.fileno())
            actual_signature = f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}"
            if actual_signature != expected_signature:
                raise HTTPException(status_code=409, detail="Bereinigte Ausgabe fehlt oder wurde seit der Validierung verändert.")
            line_number = 0
            while len(results) <= MAX_SEARCH_RESULTS:
                raw = stream.readline(MAX_LINE_BYTES + 1)
                if not raw:
                    break
                line_number += 1
                if len(raw) > MAX_LINE_BYTES:
                    raise HTTPException(status_code=422, detail="Ausgabe enthält eine Zeile oberhalb des geprüften Limits.")
                try:
                    line = raw.decode("utf-8").rstrip("\r\n")
                except UnicodeDecodeError as exc:
                    raise HTTPException(status_code=422, detail="Ausgabe ist nicht gültig UTF-8.") from exc
                try:
                    match = compiled_query.search(line, timeout=0.1)
                except TimeoutError as exc:
                    raise HTTPException(status_code=422, detail="Regex-Suche überschreitet das Zeitlimit.") from exc
                if match is not None:
                    match_at = match.start()
                    start_at = max(0, match_at - 100)
                    end_at = min(len(line), start_at + 300)
                    snippet = ("…" if start_at else "") + line[start_at:end_at] + ("…" if end_at < len(line) else "")
                    results.append({"line_number": line_number, "snippet": snippet})
    except OSError as exc:
        raise HTTPException(status_code=410, detail="Bereinigte Ausgabe konnte nicht gelesen werden.") from exc
    truncated = len(results) > MAX_SEARCH_RESULTS
    results = results[:MAX_SEARCH_RESULTS]
    return {"run_id": run_id, "query": query, "match_type": match_type, "match_count": len(results),
            "limit": MAX_SEARCH_RESULTS, "truncated": truncated, "results": results}


@router.get("/saved-searches")
def list_saved_searches(request: Request) -> list[dict]:
    actor_id, _ = _actor(request)
    initialize_review_database()
    with _db() as db:
        rows = db.execute(
            "SELECT id, name, query, match_type, created_at FROM saved_searches WHERE owner_user_id=? ORDER BY name COLLATE NOCASE",
            (actor_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/saved-searches", status_code=201)
def create_saved_search(payload: SavedSearchCreate, request: Request) -> dict:
    actor_id, actor_name = _actor(request)
    initialize_review_database()
    search_id = uuid4().hex
    try:
        with _db() as db:
            db.execute(
                "INSERT INTO saved_searches(id, owner_user_id, name, query, match_type, created_at) VALUES(?,?,?,?,?,?)",
                (search_id, actor_id, payload.name, payload.query, payload.match_type, _now()),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Ein Suchmuster mit diesem Namen existiert bereits.") from exc
    return {"id": search_id, "name": payload.name, "query": payload.query, "match_type": payload.match_type, "owner": actor_name}


@router.delete("/saved-searches/{search_id}", status_code=204)
def delete_saved_search(search_id: str, request: Request) -> None:
    actor_id, _ = _actor(request)
    with _db() as db:
        cursor = db.execute(
            "DELETE FROM saved_searches WHERE id=? AND owner_user_id=?",
            (search_id, actor_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Gespeichertes Suchmuster nicht gefunden.")


def _decide(run_id: str, action: str, payload: ReviewDecision, request: Request) -> dict:
    actor_id, actor_name = _actor(request)
    if payload.exception and action != "approve":
        raise HTTPException(status_code=422, detail="Ausnahmen sind nur bei einer begründeten Freigabe zulässig.")
    if payload.exception and not payload.exception_reason:
        raise HTTPException(status_code=422, detail="Für eine Ausnahme ist eine Begründung erforderlich.")
    if not payload.exception and payload.exception_reason:
        raise HTTPException(status_code=422, detail="Eine Ausnahmenbegründung erfordert die explizite Ausnahmeoption.")
    initialize_review_database()
    with _db() as db:
        row = db.execute("SELECT * FROM review_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Bereinigungslauf nicht gefunden.")
        if row["status"] != "pending_review":
            raise HTTPException(status_code=409, detail="Nur ausstehende Läufe können entschieden werden.")
        if action == "approve" and (not row["validated"] or row["residual_matches"] != 0):
            raise HTTPException(status_code=409, detail="Pflichtvalidierung nicht bestanden; Freigabe verweigert.")
        if action == "approve" and (
            not row["output_signature"]
            or _file_signature(Path(row["output_path"])) != row["output_signature"]
        ):
            raise HTTPException(status_code=409, detail="Bereinigte Ausgabe fehlt oder wurde seit der Validierung verändert.")
        status = {
            "approve": "approved_with_exception" if payload.exception else "approved",
            "return": "returned",
            "stop": "stopped",
        }[action]
        if action == "approve":
            _publish_approved_output(db, row)
        db.execute(
            """UPDATE review_runs SET status=?, reviewer_user_id=?,
               last_comment=?, exception_reason=? WHERE id=? AND status='pending_review'""",
            (status, actor_id, payload.comment, payload.exception_reason if payload.exception else "", run_id),
        )
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise HTTPException(status_code=409, detail="Der Lauf wurde parallel bereits entschieden.")
        _audit(db, run_id, actor_id, actor_name, action, payload.comment,
               payload.exception_reason if payload.exception else "")
        return _public_run(db.execute("SELECT * FROM review_runs WHERE id=?", (run_id,)).fetchone())


@router.post("/runs/{run_id}/approve")
def approve_run(run_id: str, payload: ReviewDecision, request: Request) -> dict:
    return _decide(run_id, "approve", payload, request)


@router.post("/runs/{run_id}/return")
def return_run(run_id: str, payload: ReviewDecision, request: Request) -> dict:
    result = _decide(run_id, "return", payload, request)
    notify_returned_run(result)
    return result


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str, payload: ReviewDecision, request: Request) -> dict:
    return _decide(run_id, "stop", payload, request)


@router.post("/runs/{run_id}/comments")
def add_review_comment(run_id: str, payload: ReviewComment, request: Request) -> dict:
    actor_id, actor_name = _actor(request)
    initialize_review_database()
    with _db() as db:
        row = db.execute("SELECT status FROM review_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Bereinigungslauf nicht gefunden.")
        if row["status"] != "pending_review":
            raise HTTPException(status_code=409, detail="Kommentare sind nur bei ausstehenden Prüfungen möglich.")
        db.execute("UPDATE review_runs SET last_comment=? WHERE id=?", (payload.comment, run_id))
        _audit(db, run_id, actor_id, actor_name, "commented", comment=payload.comment)
    return {"run_id": run_id, "comment": payload.comment}


@router.get("/audit")
def audit_log(limit: int = Query(default=100, ge=1, le=200)) -> list[dict]:
    initialize_review_database()
    with _db() as db:
        rows = db.execute(
            """SELECT id, run_id, actor_user_id, actor_username, action, comment,
                      exception_reason, created_at
               FROM review_events ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
