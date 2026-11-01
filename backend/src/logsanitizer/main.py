"""FastAPI application entry point.

Local project management and sanitization are development features. Release
controls and production security hardening remain incomplete.
"""
import asyncio
import csv
import io
import json
import os
import shutil
import sys
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from logsanitizer.auth import AuthMiddleware, initialize_auth_database
from logsanitizer.auth import router as auth_router
from logsanitizer.database import (
    FileAlreadyRegisteredError,
    FileImportRequest,
    FolderImportIssue,
    FolderImportRequest,
    FolderImportResult,
    FormatOverrideRequest,
    ImportedFile,
    Project,
    ProjectCreate,
    ProjectOutputDirectoryUpdate,
    connect_database,
    create_project,
    database_path,
    get_project,
    initialize_database,
    list_imported_files,
    list_projects,
    register_imported_file,
    update_detected_format,
    update_format_override,
    update_project_output_directory,
)
from logsanitizer.deployment import load_settings
from logsanitizer.format_validation import validate_file
from logsanitizer.job_store import (
    create_job,
    get_job,
    initialize_job_database,
    pop_recovered_job_ids,
    update_job,
)
from logsanitizer.notifications import notify_pending_review
from logsanitizer.review_workflow import create_run as create_review_run
from logsanitizer.review_workflow import fail_run as fail_review_run
from logsanitizer.review_workflow import finish_run as finish_review_run
from logsanitizer.review_workflow import initialize_review_database, is_file_approved
from logsanitizer.review_workflow import router as review_router
from logsanitizer.review_workflow import set_run_running as set_review_run_running
from logsanitizer.rule_config import (
    RuleConfig,
    find_rule_conflicts,
    load_rule_config,
    save_rule_config,
)
from logsanitizer.rule_file_preview import preview_file_window
from logsanitizer.rule_library import list_rule_categories, list_rule_templates
from logsanitizer.rule_preview import RulePreviewError, preview_rules
from logsanitizer.sanitizer import SanitizationCancelled, SanitizationError, sanitize_file


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    load_settings()
    initialize_database()
    initialize_auth_database()
    initialize_review_database()
    initialize_job_database()
    for recovered_job_id in pop_recovered_job_ids():
        fail_review_run(
            recovered_job_id,
            "failed",
            "Der Backend-Prozess wurde vor Abschluss beendet; bitte den Lauf erneut starten.",
        )
    yield


app = FastAPI(
    title="LogSanitizer API",
    version="0.1.0-dev",
    description="Local API scaffold for LogSanitizer.",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.get("/api/health", tags=["system"])
def health() -> JSONResponse:
    """Return minimal liveness status without exposing local data."""
    return JSONResponse(content={"status": "ok", "application": "LogSanitizer"})


@app.get("/api/projects", response_model=list[Project], tags=["projects"])
def projects_list() -> list[Project]:
    """List project metadata without reading project files."""
    return list_projects()


@app.post(
    "/api/projects",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
)
def projects_create(payload: ProjectCreate) -> Project:
    """Create a project metadata record; no files are imported or processed."""
    return create_project(payload)


@app.get("/api/projects/{project_id}", response_model=Project, tags=["projects"])
def projects_get(project_id: str) -> Project:
    """Return a project or a generic not-found response."""
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projekt nicht gefunden.")
    return project

@app.put("/api/projects/{project_id}/output-directory", response_model=Project, tags=["projects"])
def projects_set_output_directory(
    project_id: str, payload: ProjectOutputDirectoryUpdate
) -> Project:
    """Persist the single output directory used by all files in a project."""
    if payload.output_directory:
        directory = Path(payload.output_directory).expanduser()
        if not directory.exists() or not directory.is_dir():
            raise HTTPException(status_code=422, detail="Der Ausgabeordner muss bereits existieren.")
        if directory.is_symlink():
            raise HTTPException(status_code=422, detail="Symbolische Links sind als Ausgabeordner nicht zulässig.")
        normalized = str(directory.resolve())
    else:
        normalized = ""
    project = update_project_output_directory(project_id, normalized)
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    return project


@app.get(
    "/api/projects/{project_id}/files",
    response_model=list[ImportedFile],
    tags=["files"],
)
def project_files_list(project_id: str) -> list[ImportedFile]:
    """List registered source-file metadata for a project."""
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projekt nicht gefunden.")
    files = list_imported_files(project_id)
    for imported_file in files:
        if is_file_approved(project_id, imported_file.id):
            imported_file.state = "approved"
    return files


@app.post(
    "/api/projects/{project_id}/files",
    response_model=ImportedFile,
    status_code=status.HTTP_201_CREATED,
    tags=["files"],
)
def project_file_register(project_id: str, payload: FileImportRequest) -> ImportedFile:
    """Register a source path only; this endpoint never reads log contents."""
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projekt nicht gefunden.")

    source = Path(payload.path).expanduser()
    if not source.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Bitte einen absoluten lokalen Dateipfad angeben.",
        )
    if source.is_symlink():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Symbolische Links werden nicht als Quelldateien akzeptiert.",
        )
    try:
        resolved = source.resolve(strict=True)
        if not resolved.is_file():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Der Quellpfad muss auf eine reguläre Datei zeigen.",
            )
        return register_imported_file(project_id, resolved)
    except FileAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Diese Quelldatei ist bereits in diesem Projekt registriert.",
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quelldatei nicht gefunden.",
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf die Quelldatei.",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Quelldatei kann nicht registriert werden.",
        ) from exc


MAX_FORMAT_SAMPLE_BYTES = 64 * 1024

def _is_json_line(line: str) -> bool:
    try:
        value = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(value, (dict, list))


def detect_format_from_sample(path: Path) -> str:
    """Classify a bounded local sample without returning source content."""
    with path.open("rb") as source:
        sample = source.read(MAX_FORMAT_SAMPLE_BYTES)
    if not sample:
        # An empty log is a valid empty text file, not an unknown/binary format.
        return "text"
    try:
        text = sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "unknown"
    stripped = text.lstrip()
    if not stripped:
        return "text"
    if stripped.startswith(("<?xml", "<")):
        return "xml"
    if stripped.startswith(("{", "[")):
        try:
            _, end = json.JSONDecoder().raw_decode(stripped)
            if not stripped[end:].strip():
                return "json"
        except json.JSONDecodeError:
            pass
        lines = [line for line in stripped.splitlines() if line.strip()]
        sample_truncated = path.stat().st_size > len(sample)
        if sample_truncated and lines and not stripped.endswith(("\n", "\r")):
            lines = lines[:-1]
        if lines and all(_is_json_line(line) for line in lines):
            return "jsonl"
        if sample_truncated and path.suffix.casefold() in {".jsonl", ".ndjson"}:
            return "jsonl"
        if sample_truncated:
            # A document that extends beyond the bounded sample is classified as
            # JSON when it is not a sequence of complete JSON Lines. Full syntax
            # validation remains an explicit later step.
            return "json"
        return "unknown"
    if chr(0) in text:
        return "unknown"
    try:
        dialect = csv.Sniffer().sniff(stripped[:8192], delimiters=",;\t|")
        rows = list(csv.reader(io.StringIO(stripped[:8192]), dialect))
        if len(rows) >= 2 and len(rows[0]) > 1 and all(len(row) == len(rows[0]) for row in rows[:20]):
            return "csv"
    except csv.Error:
        pass
    return "text"


@app.post("/api/projects/{project_id}/files/{file_id}/detect-format", tags=["files"])
def project_file_detect_format(project_id: str, file_id: str) -> dict[str, str | int | None]:
    """Inspect a bounded local sample and return only its classification."""
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    with connect_database() as connection:
        row = connection.execute(
            "SELECT source_path FROM imported_files WHERE project_id = ? AND id = ?",
            (project_id, file_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Registrierte Datei nicht gefunden.")
    if is_file_approved(project_id, file_id):
        raise HTTPException(status_code=409, detail="Diese Datei wurde bereits freigegeben und ist gesperrt.")
    source = Path(row["source_path"])
    try:
        if source.is_symlink() or not source.is_file():
            raise HTTPException(status_code=422, detail="Quelldatei ist nicht mehr verfügbar oder nicht regulär.")
        detected = detect_format_from_sample(source)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Quelldatei.") from exc
    except OSError as exc:
        raise HTTPException(status_code=422, detail="Dateiformat konnte nicht geprüft werden.") from exc
    updated = update_detected_format(project_id, file_id, detected)
    if updated is None:
        raise HTTPException(status_code=404, detail="Registrierte Datei nicht gefunden.")
    return {
        "file_id": file_id,
        "detected_format": updated.detected_format,
        "format_override": updated.format_override,
        "sample_limit_bytes": MAX_FORMAT_SAMPLE_BYTES,
    }


@app.put(
    "/api/projects/{project_id}/files/{file_id}/format",
    response_model=ImportedFile,
    tags=["files"],
)
def project_file_set_format(
    project_id: str, file_id: str, payload: FormatOverrideRequest
) -> ImportedFile:
    """Persist a manual format override, or clear it with null."""
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    if is_file_approved(project_id, file_id):
        raise HTTPException(status_code=409, detail="Diese Datei wurde bereits freigegeben und ist gesperrt.")
    updated = update_format_override(project_id, file_id, payload.format_override)
    if updated is None:
        raise HTTPException(status_code=404, detail="Registrierte Datei nicht gefunden.")
    return updated


@app.post("/api/projects/{project_id}/files/{file_id}/validate-format", tags=["files"])
def project_file_validate_format(project_id: str, file_id: str) -> dict[str, str | int | bool]:
    """Validate the entire source file locally using the effective selected format."""
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    with connect_database() as connection:
        row = connection.execute(
            "SELECT source_path, detected_format, format_override, display_name, relative_path FROM imported_files "
            "WHERE project_id = ? AND id = ?",
            (project_id, file_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Registrierte Datei nicht gefunden.")
    if is_file_approved(project_id, file_id):
        raise HTTPException(status_code=409, detail="Diese Datei wurde bereits freigegeben und ist gesperrt.")
    source = Path(row["source_path"])
    if source.is_symlink() or not source.is_file():
        raise HTTPException(status_code=422, detail="Quelldatei ist nicht mehr verfügbar oder nicht regulär.")
    selected_format = row["format_override"] or row["detected_format"]
    try:
        result = validate_file(source, selected_format)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Quelldatei.") from exc
    except OSError as exc:
        raise HTTPException(status_code=422, detail="Quelldatei konnte nicht geprüft werden.") from exc
    return {"file_id": file_id, **result}


@app.get("/api/rules/library", tags=["rules"])
def rules_library_get() -> dict[str, object]:
    """Return built-in starter templates without modifying the active configuration."""
    return {"categories": list_rule_categories(), "templates": list_rule_templates()}


class RulePreviewRequest(BaseModel):
    config: RuleConfig
    sample_text: str = Field(min_length=1, max_length=65_536)
    profile_id: str | None = Field(default=None, max_length=64)
    rule_id: str | None = Field(default=None, max_length=64)


@app.post("/api/rules/preview", tags=["rules"])
def rules_preview(payload: RulePreviewRequest) -> dict[str, object]:
    """Simulate a rule or active rule set on supplied text without file or mapping writes."""
    try:
        return {
            **preview_rules(payload.sample_text, payload.config, payload.profile_id, payload.rule_id),
            "conflicts": find_rule_conflicts(payload.config),
        }
    except RulePreviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class RuleFilePreviewRequest(BaseModel):
    config: RuleConfig
    byte_offset: int = Field(default=0, ge=0)
    from_end: bool = False
    profile_id: str | None = Field(default=None, max_length=64)
    rule_id: str | None = Field(default=None, max_length=64)


@app.post("/api/projects/{project_id}/files/{file_id}/preview", tags=["files"])
def project_file_preview(project_id: str, file_id: str, payload: RuleFilePreviewRequest) -> dict[str, object]:
    """Return a bounded, read-only source window and its in-memory sanitization preview."""
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    with connect_database() as connection:
        row = connection.execute(
            "SELECT source_path, detected_format, format_override FROM imported_files "
            "WHERE project_id = ? AND id = ?",
            (project_id, file_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Registrierte Datei nicht gefunden.")
    selected_format = row["format_override"] or row["detected_format"]
    if selected_format not in {"text", "jsonl"}:
        raise HTTPException(status_code=422, detail="Die Dateivorschau unterstützt derzeit Text- und JSON-Lines-Dateien.")
    try:
        return preview_file_window(
            Path(row["source_path"]), payload.config,
            byte_offset=payload.byte_offset, from_end=payload.from_end,
            profile_id=payload.profile_id, rule_id=payload.rule_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Quelldatei.") from exc
    except OSError as exc:
        raise HTTPException(status_code=422, detail="Quelldatei konnte nicht gelesen werden.") from exc
    except RulePreviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/rules/config", response_model=RuleConfig, tags=["rules"])
def rules_config_get() -> RuleConfig:
    """Return the local versioned rule configuration."""
    try:
        return load_rule_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/rules/config/validate", tags=["rules"])
def rules_config_validate(payload: RuleConfig) -> dict[str, object]:
    """Validate schema and report exact-priority conflicts without saving."""
    conflicts = find_rule_conflicts(payload)
    return {
        "schema_version": payload.schema_version,
        "valid": not conflicts,
        "rule_count": len(payload.rules),
        "profile_count": len(payload.profiles),
        "conflicts": conflicts,
    }


@app.put("/api/rules/config", response_model=RuleConfig, tags=["rules"])
def rules_config_put(payload: RuleConfig) -> RuleConfig:
    """Persist only schema-valid, conflict-free rules using an atomic local write."""
    conflicts = find_rule_conflicts(payload)
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Regelkonflikte müssen vor dem Speichern behoben werden.", "conflicts": conflicts},
        )
    try:
        save_rule_config(payload)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Regelkonfiguration konnte nicht gespeichert werden.") from exc
    return payload


class SanitizationRequest(BaseModel):
    output_path: str = Field(min_length=1, max_length=4096)
    profile_id: str | None = Field(default=None, max_length=64)
    retry_of_run_id: str | None = Field(default=None, max_length=80)



def _staging_output_path(project_id: str, run_id: str, output_name: str) -> Path:
    """Create an isolated per-run work directory outside the configured output folder."""
    work_root = database_path().parent / "projects" / project_id / "work"
    work_root.mkdir(parents=True, exist_ok=True)
    if work_root.is_symlink():
        raise HTTPException(status_code=422, detail="Der Arbeitsordner darf kein symbolischer Link sein.")
    run_directory = work_root / run_id
    run_directory.mkdir()
    return run_directory / output_name


def _relative_project_source_path(project_id: str, source: Path, stored_relative_path: str = "") -> Path:
    """Return a validated project-relative path without exposing absolute source paths."""
    relative = PurePosixPath(stored_relative_path.replace("\\", "/")) if stored_relative_path else None
    if relative is not None and not relative.is_absolute() and relative.parts and all(
        part not in {"", ".", ".."} and ":" not in part for part in relative.parts
    ):
        return Path(*relative.parts)
    sources_root = (database_path().parent / "projects" / project_id / "sources").resolve()
    try:
        return source.resolve(strict=False).relative_to(sources_root)
    except ValueError:
        # Backend-path imports outside the project workspace keep only their basename.
        return Path(source.name)


@app.post(
    "/api/projects/{project_id}/files/{file_id}/sanitize-jobs",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["sanitization"],
)
def project_file_sanitize_start(
    project_id: str,
    file_id: str,
    payload: SanitizationRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict[str, object]:
    """Start a cancellable local sanitization job and return immediately."""
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    with connect_database() as connection:
        row = connection.execute(
            "SELECT source_path, detected_format, format_override, display_name, relative_path FROM imported_files "
            "WHERE project_id = ? AND id = ?",
            (project_id, file_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Registrierte Datei nicht gefunden.")
    if is_file_approved(project_id, file_id):
        raise HTTPException(status_code=409, detail="Diese Datei wurde bereits freigegeben und ist für weitere Bereinigungen gesperrt.")
    source = Path(row["source_path"])
    output = Path(payload.output_path).expanduser()
    if not output.is_absolute():
        raise HTTPException(status_code=422, detail="Bitte einen absoluten Zielpfad angeben.")
    output_root = Path(project.output_directory).expanduser()
    if not project.output_directory or not output_root.is_dir():
        raise HTTPException(status_code=422, detail="Der Projekt-Ausgabeordner muss festgelegt werden und existieren.")
    try:
        resolved_root = output_root.resolve(strict=True)
        relative_source = _relative_project_source_path(project_id, source, row["relative_path"])
        expected_output = (resolved_root / relative_source).resolve(strict=False)
        if output.resolve(strict=False) != expected_output:
            raise HTTPException(status_code=422, detail="Die Ausgabedatei muss die relative Quellpfadstruktur im Projekt-Ausgabeordner beibehalten.")
        expected_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = expected_output.parent.resolve(strict=True)
        if not resolved_parent.is_relative_to(resolved_root):
            raise HTTPException(status_code=422, detail="Der Ausgabepfad liegt außerhalb des Projekt-Ausgabeordners.")
        output = resolved_parent / expected_output.name
    except OSError as exc:
        raise HTTPException(status_code=422, detail="Die Ausgabeverzeichnisstruktur konnte nicht angelegt werden.") from exc
    if output.resolve(strict=False) == source.resolve(strict=False):
        raise HTTPException(status_code=422, detail="Quell- und Zieldatei dürfen nicht identisch sein.")
    if output.is_symlink() or output.exists():
        raise HTTPException(status_code=409, detail="Die Zieldatei existiert bereits.")
    selected_format = row["format_override"] or row["detected_format"]
    if source.is_symlink() or not source.is_file():
        raise HTTPException(status_code=422, detail="Quelldatei ist nicht mehr verfügbar oder nicht regulär.")
    if selected_format not in {"text", "jsonl", "json"}:
        raise HTTPException(status_code=422, detail="Unterstützt werden derzeit Text, JSON und JSON Lines.")
    try:
        config = load_rule_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Regelkonfiguration kann nicht gelesen werden.") from exc
    if find_rule_conflicts(config):
        raise HTTPException(status_code=409, detail="Regelkonflikte müssen vor der Bereinigung behoben werden.")
    if payload.profile_id is not None and payload.profile_id not in {p.id for p in config.profiles}:
        raise HTTPException(status_code=422, detail="Das angegebene Quellprofil ist nicht definiert.")

    job_id = uuid.uuid4().hex
    publish_output = output
    try:
        work_output = _staging_output_path(project_id, job_id, output.name)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Arbeitsordner konnte nicht angelegt werden.") from exc
    user = request.state.user
    try:
        create_review_run(
            job_id, project_id, file_id, row["display_name"], work_output,
            int(user["id"]), str(user["username"]), payload.retry_of_run_id,
            publish_path=publish_output,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        create_job(job_id, project_id, file_id, source, work_output, source.stat().st_size)
    except (OSError, RuntimeError) as exc:
        fail_review_run(job_id, "failed", "Der Laufstatus konnte nicht dauerhaft gespeichert werden.")
        raise HTTPException(status_code=500, detail="Laufstatus konnte nicht gespeichert werden.") from exc
    with _SANITIZATION_LOCK:
        _SANITIZATION_CANCEL[job_id] = threading.Event()
    background_tasks.add_task(
        _run_sanitization_job, job_id, project_id, file_id, source, work_output,
        config, payload.profile_id, selected_format,
    )
    return {"id": job_id, "status": "queued", "status_url": f"/api/projects/{project_id}/files/{file_id}/sanitize-jobs/{job_id}"}


@app.get(
    "/api/projects/{project_id}/files/{file_id}/sanitize-jobs/{job_id}",
    tags=["sanitization"],
)
def project_file_sanitize_status(project_id: str, file_id: str, job_id: str) -> dict[str, object]:
    """Return progress and status without exposing source paths or log contents."""
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    job = get_job(job_id)
    if job is None or job["project_id"] != project_id or job["file_id"] != file_id:
        raise HTTPException(status_code=404, detail="Bereinigungslauf nicht gefunden.")
    return {key: value for key, value in job.items() if key not in {"project_id", "file_id"}}


@app.post(
    "/api/projects/{project_id}/files/{file_id}/sanitize-jobs/{job_id}/cancel",
    tags=["sanitization"],
)
def project_file_sanitize_cancel(project_id: str, file_id: str, job_id: str) -> dict[str, object]:
    """Request cooperative cancellation; the worker removes its staging file."""
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    job = get_job(job_id)
    if job is None or job["project_id"] != project_id or job["file_id"] != file_id:
        raise HTTPException(status_code=404, detail="Bereinigungslauf nicht gefunden.")
    if job["status"] in {"completed", "failed", "cancelled", "interrupted"}:
        return {"id": job_id, "status": job["status"]}
    with _SANITIZATION_LOCK:
        event = _SANITIZATION_CANCEL.get(job_id)
        if event is not None:
            event.set()
            update_job(job_id, status="cancelling", phase="cancelling")
    return {"id": job_id, "status": "cancelling"}


@app.post("/api/projects/{project_id}/files/{file_id}/sanitize", tags=["sanitization"])
def project_file_sanitize(
    project_id: str, file_id: str, payload: SanitizationRequest, request: Request
) -> dict[str, int | str | bool]:
    """Apply local rules to supported UTF-8 text, JSON and JSONL files."""
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden.")
    with connect_database() as connection:
        row = connection.execute(
            "SELECT source_path, detected_format, format_override, display_name FROM imported_files "
            "WHERE project_id = ? AND id = ?",
            (project_id, file_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Registrierte Datei nicht gefunden.")
    if is_file_approved(project_id, file_id):
        raise HTTPException(status_code=409, detail="Diese Datei wurde bereits freigegeben und ist für weitere Bereinigungen gesperrt.")

    source = Path(row["source_path"])
    output = Path(payload.output_path).expanduser()
    if not output.is_absolute():
        raise HTTPException(status_code=422, detail="Bitte einen absoluten Zielpfad angeben.")
    if not output.parent.is_dir():
        raise HTTPException(status_code=422, detail="Der Zielordner muss bereits existieren.")
    if output.resolve(strict=False) == source.resolve(strict=False):
        raise HTTPException(status_code=422, detail="Quell- und Zieldatei dürfen nicht identisch sein.")
    if output.exists():
        raise HTTPException(status_code=409, detail="Die Zieldatei existiert bereits.")
    selected_format = row["format_override"] or row["detected_format"]
    if selected_format not in {"text", "jsonl", "json"}:
        raise HTTPException(
            status_code=422,
            detail="Vor der Bereinigung muss das Format als Text, JSON oder JSON Lines ausgewählt bzw. erkannt sein.",
        )
    if not output.is_absolute():
        raise HTTPException(status_code=422, detail="Bitte einen absoluten Zielpfad angeben.")
    try:
        config = load_rule_config()
        if find_rule_conflicts(config):
            raise HTTPException(status_code=409, detail="Regelkonflikte müssen vor der Bereinigung behoben werden.")
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Regelkonfiguration kann nicht gelesen werden.") from exc
    user = request.state.user
    run_id = uuid.uuid4().hex
    try:
        work_output = _staging_output_path(project_id, run_id, output.name)
        create_review_run(
            run_id, project_id, file_id, row["display_name"], work_output,
            int(user["id"]), str(user["username"]), payload.retry_of_run_id,
            publish_path=output,
        )
        set_review_run_running(run_id)
        result = sanitize_file(source, work_output, config, payload.profile_id, selected_format, project_id)
        review_run = finish_review_run(run_id, result)
        notify_pending_review(review_run)
        return {
            "file_id": file_id,
            "output_name": output.name,
            "review_run_id": run_id,
            "review_status": review_run["status"],
            **result,
        }
    except SanitizationError as exc:
        fail_review_run(run_id, "failed", "Sanitisierung oder Pflichtvalidierung fehlgeschlagen.")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileExistsError as exc:
        fail_review_run(run_id, "failed", "Die Zieldatei existiert bereits.")
        raise HTTPException(status_code=409, detail="Die Zieldatei existiert bereits.") from exc
    except PermissionError as exc:
        fail_review_run(run_id, "failed", "Kein Zugriff auf Quell- oder Zieldatei.")
        raise HTTPException(status_code=403, detail="Kein Zugriff auf Quell- oder Zieldatei.") from exc
    except RuntimeError as exc:
        fail_review_run(run_id, "failed", "Datei konnte nicht sicher verarbeitet werden.")
        raise HTTPException(status_code=500, detail="Regelkonfiguration kann nicht gelesen werden.") from exc
    except OSError as exc:
        fail_review_run(run_id, "failed", "Datei konnte nicht sicher verarbeitet werden.")
        raise HTTPException(status_code=422, detail="Datei konnte nicht bereinigt werden.") from exc



_SANITIZATION_CANCEL: dict[str, threading.Event] = {}
_SANITIZATION_LAST_PERSISTED: dict[str, tuple[int, str]] = {}
_SANITIZATION_LOCK = threading.Lock()


def _set_job(job_id: str, **changes: object) -> None:
    # Durable state is authoritative; the in-memory dictionary only holds cancellation events.
    update_job(job_id, **changes)


def _job_progress(job_id: str, progress: dict[str, int | str]) -> None:
    # Persist at phase boundaries and in 1 MiB increments, not on every log line.
    processed = int(progress.get("processed_bytes", 0))
    phase = str(progress.get("phase", ""))
    with _SANITIZATION_LOCK:
        previous_bytes, previous_phase = _SANITIZATION_LAST_PERSISTED.get(job_id, (0, ""))
        if phase == previous_phase and processed - previous_bytes < 1024 * 1024:
            return
        _SANITIZATION_LAST_PERSISTED[job_id] = (processed, phase)
    _set_job(job_id, **progress)


def _run_sanitization_job(
    job_id: str,
    project_id: str,
    file_id: str,
    source: Path,
    output: Path,
    config: RuleConfig,
    profile_id: str | None,
    selected_format: str,
) -> None:
    with _SANITIZATION_LOCK:
        cancel_event = _SANITIZATION_CANCEL.get(job_id)
    if cancel_event is None:
        fail_review_run(job_id, "failed", "Abbruchsteuerung des Laufs ist nicht verfügbar.")
        _set_job(job_id, status="failed", phase="failed", error="Abbruchsteuerung des Laufs ist nicht verfügbar.")
        return
    _set_job(job_id, status="running", phase="sanitizing")
    set_review_run_running(job_id)
    try:
        result = sanitize_file(
            source,
            output,
            config,
            profile_id,
            selected_format,
            project_id,
            progress_callback=lambda progress: _job_progress(job_id, progress),
            cancel_check=cancel_event.is_set,
        )
        review_run = finish_review_run(job_id, result)
        _set_job(job_id, status="completed", phase="completed", result={
            "file_id": file_id, "output_name": output.name, "review_status": review_run["status"], **result,
        })
        notify_pending_review(review_run)
    except SanitizationCancelled:
        fail_review_run(job_id, "cancelled", "Bereinigung wurde abgebrochen.")
        _set_job(job_id, status="cancelled", phase="cancelled", error="Bereinigung wurde abgebrochen.")
    except FileExistsError:
        fail_review_run(job_id, "failed", "Die Zieldatei existiert bereits.")
        _set_job(job_id, status="failed", phase="failed", error="Die Zieldatei existiert bereits.")
    except SanitizationError as exc:
        fail_review_run(job_id, "failed", "Sanitisierung oder Pflichtvalidierung fehlgeschlagen.")
        _set_job(job_id, status="failed", phase="failed", error=str(exc))
    except PermissionError:
        fail_review_run(job_id, "failed", "Kein Zugriff auf Quell- oder Zieldatei.")
        _set_job(job_id, status="failed", phase="failed", error="Kein Zugriff auf Quell- oder Zieldatei.")
    except (OSError, RuntimeError):
        fail_review_run(job_id, "failed", "Datei konnte nicht sicher verarbeitet werden.")
        _set_job(job_id, status="failed", phase="failed", error="Datei konnte nicht bereinigt werden.")
    finally:
        with _SANITIZATION_LOCK:
            _SANITIZATION_CANCEL.pop(job_id, None)
            _SANITIZATION_LAST_PERSISTED.pop(job_id, None)


MAX_FOLDER_FILES = 5000


@app.post(
    "/api/projects/{project_id}/files/import-folder",
    response_model=FolderImportResult,
    status_code=status.HTTP_200_OK,
    tags=["files"],
)
def project_folder_import(
    project_id: str, payload: FolderImportRequest
) -> FolderImportResult:
    """Register files under a folder; never reads their contents."""
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projekt nicht gefunden.")

    folder = Path(payload.path).expanduser()
    if not folder.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Bitte einen absoluten lokalen Ordnerpfad angeben.",
        )
    if folder.is_symlink():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Symbolische Links werden nicht als Importordner akzeptiert.",
        )
    try:
        folder = folder.resolve(strict=True)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Importordner nicht gefunden."
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Kein Zugriff auf den Importordner."
        ) from exc
    if not folder.is_dir():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Der Importpfad muss auf einen Ordner zeigen.",
        )

    registered: list[ImportedFile] = []
    issues: list[FolderImportIssue] = []
    candidates = 0

    def walk_error(error: OSError) -> None:
        issues.append(
            FolderImportIssue(
                file_name=Path(error.filename or folder.name).name,
                reason="Ordner kann nicht gelesen werden.",
            )
        )

    for current_root, dir_names, file_names in os.walk(
        folder, topdown=True, followlinks=False, onerror=walk_error
    ):
        current = Path(current_root)
        blocked_dirs = []
        for name in dir_names:
            path = current / name
            if path.is_symlink():
                issues.append(
                    FolderImportIssue(file_name=name, reason="Symbolischer Ordnerlink übersprungen.")
                )
            else:
                blocked_dirs.append(name)
        dir_names[:] = blocked_dirs if payload.recursive else []

        for name in sorted(file_names, key=str.casefold):
            candidate = current / name
            candidates += 1
            if candidates > MAX_FOLDER_FILES:
                issues.append(
                    FolderImportIssue(
                        file_name=name,
                        reason=f"Limit von {MAX_FOLDER_FILES} Dateien erreicht; Rest übersprungen.",
                    )
                )
                dir_names[:] = []
                break
            if candidate.is_symlink():
                issues.append(
                    FolderImportIssue(file_name=name, reason="Symbolischer Datei-Link übersprungen.")
                )
                continue
            try:
                resolved = candidate.resolve(strict=True)
                if not resolved.is_file():
                    issues.append(
                        FolderImportIssue(file_name=name, reason="Keine reguläre Datei.")
                    )
                    continue
                registered.append(register_imported_file(project_id, resolved, candidate.relative_to(folder).as_posix()))
            except FileAlreadyRegisteredError:
                issues.append(
                    FolderImportIssue(file_name=name, reason="Bereits in diesem Projekt registriert.")
                )
            except PermissionError:
                issues.append(
                    FolderImportIssue(file_name=name, reason="Kein Zugriff auf die Datei.")
                )
            except FileNotFoundError:
                issues.append(
                    FolderImportIssue(file_name=name, reason="Datei wurde während des Imports entfernt.")
                )
            except OSError:
                issues.append(
                    FolderImportIssue(file_name=name, reason="Datei kann nicht registriert werden.")
                )

        if candidates > MAX_FOLDER_FILES:
            break

    return FolderImportResult(
        registered_count=len(registered),
        skipped_count=len(issues),
        registered_files=registered,
        issues=issues,
        limit_reached=candidates > MAX_FOLDER_FILES,
    )



MAX_UPLOAD_BYTES = 5 * 1024 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
UPLOAD_DISK_RESERVE_BYTES = 16 * 1024 * 1024


def _upload_size(upload: UploadFile) -> int:
    """Return the size of a spooled upload without changing its read position."""
    if upload.size is not None:
        return upload.size
    position = upload.file.tell()
    upload.file.seek(0, os.SEEK_END)
    size = upload.file.tell()
    upload.file.seek(position)
    return size


def _copy_upload_to_temporary(source: BinaryIO, destination: Path) -> int:
    """Copy a spooled upload to disk without buffering the full file in memory."""
    total_bytes = 0
    with destination.open("xb") as output:
        while chunk := source.read(UPLOAD_CHUNK_BYTES):
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_BYTES:
                raise ValueError("Datei überschreitet das Limit von 5 GiB.")
            output.write(chunk)
    return total_bytes


@app.post(
    "/api/projects/{project_id}/files/upload",
    response_model=FolderImportResult,
    tags=["files"],
)
async def project_files_upload(
    project_id: str,
    files: list[UploadFile] = File(...),  # noqa: B008
    relative_paths: str = Form("[]"),
) -> FolderImportResult:
    """Copy browser-selected files into the project workspace using bounded chunks."""
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projekt nicht gefunden.")
    try:
        requested_paths = json.loads(relative_paths)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dateiliste ist ungültig.",
        ) from exc
    if (
        not isinstance(requested_paths, list)
        or len(requested_paths) != len(files)
        or any(not isinstance(item, str) or not item.strip() for item in requested_paths)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dateinamen und Uploads stimmen nicht überein.",
        )

    root = (database_path().parent / "projects" / project_id / "sources").resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidate_uploads = files[:MAX_FOLDER_FILES]
    upload_sizes = [_upload_size(upload) for upload in candidate_uploads]
    required_bytes = sum(size for size in upload_sizes if size <= MAX_UPLOAD_BYTES)
    reserve_bytes = max(UPLOAD_DISK_RESERVE_BYTES, int(required_bytes * 0.05))
    available_bytes = shutil.disk_usage(root).free
    if available_bytes < required_bytes + reserve_bytes:
        for upload in files:
            await upload.close()
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=(
                "Nicht genügend freier Speicherplatz auf dem Zielsystem. "
                f"Benötigt: {required_bytes + reserve_bytes} Byte "
                f"(einschließlich Reserve), verfügbar: {available_bytes} Byte."
            ),
        )
    registered: list[ImportedFile] = []
    issues: list[FolderImportIssue] = []
    limit_reached = len(files) > MAX_FOLDER_FILES

    for index, upload in enumerate(candidate_uploads):
        raw_relative = requested_paths[index].replace("\\", "/")
        relative = PurePosixPath(raw_relative)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} or ":" in part for part in relative.parts)
        ):
            issues.append(
                FolderImportIssue(file_name=upload.filename or "Unbekannte Datei", reason="Ungültiger relativer Dateipfad.")
            )
            await upload.close()
            continue

        destination = (root / Path(*relative.parts)).resolve()
        if not destination.is_relative_to(root):
            issues.append(
                FolderImportIssue(file_name=upload.filename or relative.name, reason="Dateipfad liegt außerhalb des Projektbereichs.")
            )
            await upload.close()
            continue
        if destination.exists():
            issues.append(
                FolderImportIssue(file_name=relative.name, reason="Datei ist im Projektbereich bereits vorhanden.")
            )
            await upload.close()
            continue

        upload_size = upload_sizes[index]
        if upload_size > MAX_UPLOAD_BYTES:
            issues.append(
                FolderImportIssue(file_name=relative.name, reason="Datei überschreitet das Limit von 5 GiB.")
            )
            await upload.close()
            continue

        if shutil.disk_usage(root).free < upload_size + reserve_bytes:
            issues.append(
                FolderImportIssue(
                    file_name=relative.name,
                    reason="Nicht genügend freier Speicherplatz auf dem Zielsystem für diese Datei.",
                )
            )
            await upload.close()
            continue

        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(_copy_upload_to_temporary, upload.file, temporary)
            os.replace(temporary, destination)
            try:
                registered.append(register_imported_file(project_id, destination, relative.as_posix()))
            except FileAlreadyRegisteredError:
                destination.unlink(missing_ok=True)
                issues.append(
                    FolderImportIssue(file_name=relative.name, reason="Bereits in diesem Projekt registriert.")
                )
        except ValueError as exc:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            issues.append(FolderImportIssue(file_name=relative.name, reason=str(exc)))
        except OSError:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            issues.append(
                FolderImportIssue(file_name=relative.name, reason="Datei konnte nicht vollständig übernommen werden.")
            )
        except Exception:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

    if limit_reached:
        for upload in files[MAX_FOLDER_FILES:]:
            issues.append(
                FolderImportIssue(
                    file_name=upload.filename or "Unbekannte Datei",
                    reason=f"Limit von {MAX_FOLDER_FILES} Dateien erreicht; Rest übersprungen.",
                )
            )
            await upload.close()

    return FolderImportResult(
        registered_count=len(registered),
        skipped_count=len(issues),
        registered_files=registered,
        issues=issues,
        limit_reached=limit_reached,
    )


# All API routes except liveness and login require a valid local session.
app.include_router(review_router)
app.include_router(auth_router)
app.add_middleware(AuthMiddleware)


def _frontend_dist() -> Path | None:
    candidates = (
        Path(__file__).resolve().parents[3] / "frontend" / "dist",
        Path(__file__).resolve().parents[1] / "frontend" / "dist",
        Path(sys.executable).resolve().parent / "frontend" / "dist",
    )
    return next(
        (candidate for candidate in candidates if (candidate / "index.html").is_file()),
        None,
    )


_frontend_path = _frontend_dist()
if _frontend_path is not None:
    app.mount("/", StaticFiles(directory=str(_frontend_path), html=True), name="frontend")
