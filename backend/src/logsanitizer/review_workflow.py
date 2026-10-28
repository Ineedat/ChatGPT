"""Persistent review workflow, literal output sampling, and append-only audit events.

Only sanitized output paths are searchable; original source paths and log contents
are never returned by review metadata endpoints.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

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
            created_at TEXT NOT NULL,
            UNIQUE(owner_user_id, name)
        );
        """)
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
               parent_run_id: str | None = None) -> dict:
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
               (id, project_id, file_id, display_name, output_name, output_path, status,
                actor_user_id, actor_username, parent_run_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
            (run_id, project_id, file_id, display_name, output_path.name,
             str(output_path), actor_id, actor_name, parent_run_id, _now()),
        )
        _audit(db, run_id, actor_id, actor_name, "queued",
               comment=f"Überarbeitung von Lauf {parent_run_id}" if parent_run_id else "")
        return _public_run(db.execute("SELECT * FROM review_runs WHERE id=?", (run_id,)).fetchone())


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
        validated = bool(result.get("validated")) and int(result.get("residual_matches", 1)) == 0
        if not validated:
            status = "failed"
        db.execute(
            """UPDATE review_runs SET status=?, completed_at=?, input_bytes=?, output_bytes=?,
               lines_processed=?, replacements=?, validated=?, residual_matches=?, validation_scope=?
               WHERE id=?""",
            (status, _now(), int(result.get("input_bytes", 0)), int(result.get("output_bytes", 0)),
             int(result.get("lines_processed", 0)), int(result.get("replacements", 0)),
             int(validated), int(result.get("residual_matches", 0)),
             str(result.get("validation_scope", "")), run_id),
        )
        if status == "approved":
            _audit(db, run_id, None, "system", "auto_approved",
                   comment="Keine aktive Reviewer-/Approver-Zuweisung; Pflichtvalidierung bestanden.")
        else:
            _audit(db, run_id, None, "system", "pending_review",
                   comment="Pflichtvalidierung bestanden; bewusste Freigabe erforderlich.")
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
    )}


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
                "SELECT query FROM saved_searches WHERE id=? AND owner_user_id=?",
                (saved_search_id, actor_id),
            ).fetchone()
            if saved is None:
                raise HTTPException(status_code=404, detail="Gespeichertes Suchmuster nicht gefunden.")
            query = str(saved["query"])
        else:
            query = str(q).strip()
        if not query or len(query) > 200 or any(ord(char) < 32 for char in query):
            raise HTTPException(status_code=422, detail="Ungültiger Suchbegriff.")
        output_path = Path(row["output_path"])
    if output_path.is_symlink() or not output_path.is_file():
        raise HTTPException(status_code=410, detail="Bereinigte Ausgabe ist nicht mehr verfügbar.")
    results = []
    needle = query.casefold()
    try:
        with output_path.open("rb") as stream:
            line_number = 0
            while len(results) < MAX_SEARCH_RESULTS:
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
                if needle in line.casefold():
                    results.append({"line_number": line_number, "snippet": line[:300]})
    except OSError as exc:
        raise HTTPException(status_code=410, detail="Bereinigte Ausgabe konnte nicht gelesen werden.") from exc
    return {"run_id": run_id, "query": query, "match_count": len(results),
            "limit": MAX_SEARCH_RESULTS, "truncated": len(results) == MAX_SEARCH_RESULTS,
            "results": results}


@router.get("/saved-searches")
def list_saved_searches(request: Request) -> list[dict]:
    actor_id, _ = _actor(request)
    initialize_review_database()
    with _db() as db:
        rows = db.execute(
            "SELECT id, name, query, created_at FROM saved_searches WHERE owner_user_id=? ORDER BY name COLLATE NOCASE",
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
                "INSERT INTO saved_searches(id, owner_user_id, name, query, created_at) VALUES(?,?,?,?,?)",
                (search_id, actor_id, payload.name, payload.query, _now()),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Ein Suchmuster mit diesem Namen existiert bereits.") from exc
    return {"id": search_id, "name": payload.name, "query": payload.query, "owner": actor_name}


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
        status = {
            "approve": "approved_with_exception" if payload.exception else "approved",
            "return": "returned",
            "stop": "stopped",
        }[action]
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
    return _decide(run_id, "return", payload, request)


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
