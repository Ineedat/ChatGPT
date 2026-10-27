"""FastAPI application entry point.

Development scaffold only: sanitization, authentication, and release controls
are not implemented yet.
"""
import os
import csv
import io
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from logsanitizer.database import (
    FileAlreadyRegisteredError,
    FileImportRequest,
    FolderImportIssue,
    FolderImportRequest,
    FolderImportResult,
    ImportedFile,
    Project,
    ProjectCreate,
    create_project,
    connect_database,
    get_project,
    initialize_database,
    list_imported_files,
    list_projects,
    register_imported_file,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_database()
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
def project_file_detect_format(project_id: str, file_id: str) -> dict[str, str]:
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
    return {"file_id": file_id, "detected_format": detected, "sample_limit_bytes": str(MAX_FORMAT_SAMPLE_BYTES)}


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
