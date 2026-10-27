"""FastAPI application entry point.

Development scaffold only: sanitization, authentication, and release controls
are not implemented yet.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from logsanitizer.database import (
    FileImportRequest,
    ImportedFile,
    Project,
    ProjectCreate,
    create_project,
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
