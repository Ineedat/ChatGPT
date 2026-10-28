"""FastAPI application entry point.

Local project management and sanitization are development features. Release
controls and production security hardening remain incomplete.
"""
import csv
import io
import json
import os
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
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
    connect_database,
    create_project,
    get_project,
    initialize_database,
    list_imported_files,
    list_projects,
    register_imported_file,
    update_detected_format,
    update_format_override,
)
from logsanitizer.format_validation import validate_file
from logsanitizer.rule_config import (
    RuleConfig,
    find_rule_conflicts,
    load_rule_config,
    save_rule_config,
)
from logsanitizer.sanitizer import SanitizationCancelled, SanitizationError, sanitize_file


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    initialize_auth_database()
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


@app.get(
    "/api/projects/{project_id}/files",
    response_model=list[ImportedFile],
    tags=["files"],
)
def project_files_list(project_id: str) -> list[ImportedFile]:
    """List registered source-file metadata for a project."""
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projekt nicht gefunden.")
    return list_imported_files(project_id)


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
        return "unknown"
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
        if len(lines) > 1 and all(_is_json_line(line) for line in lines):
            return "jsonl"
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
    updated = update_format_override(project_id, file_id, payload.format_override)
    if updated is None:
        raise HTTPException(status_code=404, detail="Registrierte Datei nicht gefunden.")
    return updated


@app.post("/api/projects/{project_id}/files/{file_id}/validate-format", tags=["files"])
def project_file_validate_format(project_id: str, file_id: str) -> dict[str, str | int | bool]:
    """Validate the entire source file locally using the effective selected format."""
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
) -> dict[str, object]:
    """Start a cancellable local sanitization job and return immediately."""
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
    source = Path(row["source_path"])
    output = Path(payload.output_path).expanduser()
    selected_format = row["format_override"] or row["detected_format"]
    if source.is_symlink() or not source.is_file():
        raise HTTPException(status_code=422, detail="Quelldatei ist nicht mehr verfügbar oder nicht regulär.")
    if selected_format not in {"text", "jsonl"}:
        raise HTTPException(status_code=422, detail="Unterstützt werden derzeit nur Text und JSON Lines.")
    if not output.is_absolute():
        raise HTTPException(status_code=422, detail="Bitte einen absoluten Zielpfad angeben.")
    if output.is_symlink() or output.exists():
        raise HTTPException(status_code=409, detail="Die Zieldatei existiert bereits.")
    if not output.parent.is_dir():
        raise HTTPException(status_code=422, detail="Der Zielordner muss bereits existieren.")
    try:
        config = load_rule_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Regelkonfiguration kann nicht gelesen werden.") from exc
    if find_rule_conflicts(config):
        raise HTTPException(status_code=409, detail="Regelkonflikte müssen vor der Bereinigung behoben werden.")
    if payload.profile_id is not None and payload.profile_id not in {p.id for p in config.profiles}:
        raise HTTPException(status_code=422, detail="Das angegebene Quellprofil ist nicht definiert.")

    job_id = uuid.uuid4().hex
    with _SANITIZATION_LOCK:
        _SANITIZATION_JOBS[job_id] = {
            "id": job_id,
            "project_id": project_id,
            "file_id": file_id,
            "status": "queued",
            "phase": "queued",
            "processed_bytes": 0,
            "total_bytes": source.stat().st_size,
            "lines_processed": 0,
            "created_at": datetime.now(UTC).isoformat(),
        }
        _SANITIZATION_CANCEL[job_id] = threading.Event()
    background_tasks.add_task(
        _run_sanitization_job, job_id, project_id, file_id, source, output,
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
    with _SANITIZATION_LOCK:
        job = _SANITIZATION_JOBS.get(job_id)
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
    with _SANITIZATION_LOCK:
        job = _SANITIZATION_JOBS.get(job_id)
        if job is None or job["project_id"] != project_id or job["file_id"] != file_id:
            raise HTTPException(status_code=404, detail="Bereinigungslauf nicht gefunden.")
        if job["status"] in {"completed", "failed", "cancelled"}:
            return {"id": job_id, "status": job["status"]}
        event = _SANITIZATION_CANCEL.get(job_id)
        if event is not None:
            event.set()
            job["status"] = "cancelling"
    return {"id": job_id, "status": "cancelling"}


@app.post("/api/projects/{project_id}/files/{file_id}/sanitize", tags=["sanitization"])
def project_file_sanitize(
    project_id: str, file_id: str, payload: SanitizationRequest
) -> dict[str, int | str]:
    """Apply local rules to supported UTF-8 text/JSONL and write a separate output file."""
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

    source = Path(row["source_path"])
    output = Path(payload.output_path).expanduser()
    selected_format = row["format_override"] or row["detected_format"]
    if selected_format not in {"text", "jsonl"}:
        raise HTTPException(
            status_code=422,
            detail="Vor der Bereinigung muss das Format als Text oder JSON Lines ausgewählt bzw. erkannt sein.",
        )
    if not output.is_absolute():
        raise HTTPException(status_code=422, detail="Bitte einen absoluten Zielpfad angeben.")
    try:
        config = load_rule_config()
        if find_rule_conflicts(config):
            raise HTTPException(status_code=409, detail="Regelkonflikte müssen vor der Bereinigung behoben werden.")
        return {
            "file_id": file_id,
            "output_name": output.name,
            **sanitize_file(source, output, config, payload.profile_id, selected_format, project_id),
        }
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="Die Zieldatei existiert bereits.") from exc
    except SanitizationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf Quell- oder Zieldatei.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Regelkonfiguration kann nicht gelesen werden.") from exc
    except OSError as exc:
        raise HTTPException(status_code=422, detail="Datei konnte nicht bereinigt werden.") from exc



_SANITIZATION_JOBS: dict[str, dict[str, object]] = {}
_SANITIZATION_CANCEL: dict[str, threading.Event] = {}
_SANITIZATION_LOCK = threading.Lock()


def _set_job(job_id: str, **changes: object) -> None:
    with _SANITIZATION_LOCK:
        if job_id in _SANITIZATION_JOBS:
            _SANITIZATION_JOBS[job_id].update(changes)


def _job_progress(job_id: str, progress: dict[str, int | str]) -> None:
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
    cancel_event = _SANITIZATION_CANCEL[job_id]
    _set_job(job_id, status="running", phase="sanitizing")
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
        _set_job(job_id, status="completed", phase="completed", result={
            "file_id": file_id, "output_name": output.name, **result,
        })
    except SanitizationCancelled:
        _set_job(job_id, status="cancelled", phase="cancelled", error="Bereinigung wurde abgebrochen.")
    except FileExistsError:
        _set_job(job_id, status="failed", phase="failed", error="Die Zieldatei existiert bereits.")
    except SanitizationError as exc:
        _set_job(job_id, status="failed", phase="failed", error=str(exc))
    except PermissionError:
        _set_job(job_id, status="failed", phase="failed", error="Kein Zugriff auf Quell- oder Zieldatei.")
    except (OSError, RuntimeError):
        _set_job(job_id, status="failed", phase="failed", error="Datei konnte nicht bereinigt werden.")
    finally:
        with _SANITIZATION_LOCK:
            _SANITIZATION_CANCEL.pop(job_id, None)


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
                registered.append(register_imported_file(project_id, resolved))
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


# All API routes except liveness and login require a valid local session.
app.include_router(auth_router)
app.add_middleware(AuthMiddleware)
