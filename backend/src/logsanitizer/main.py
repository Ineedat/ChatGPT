"""FastAPI application entry point.

Development scaffold only: sanitization, authentication, and release controls
are not implemented yet.
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from logsanitizer.database import (
    Project,
    ProjectCreate,
    create_project,
    get_project,
    initialize_database,
    list_projects,
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
