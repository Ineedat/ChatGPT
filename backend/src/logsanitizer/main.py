"""FastAPI application entry point.

Development scaffold only: sanitization, authentication, and release controls
are not implemented yet.
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(
    title="LogSanitizer API",
    version="0.1.0-dev",
    description="Local API scaffold for LogSanitizer.",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)


@app.get("/api/health", tags=["system"])
def health() -> JSONResponse:
    """Return minimal liveness status without exposing local data."""
    return JSONResponse(content={"status": "ok", "application": "LogSanitizer"})
