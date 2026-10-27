# Backend

From this directory:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn logsanitizer.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: http://127.0.0.1:8000/api/health. API docs: http://127.0.0.1:8000/api/docs.

## Project metadata

The first SQLite schema stores project metadata only. By default the database is
`~/.logsanitizer/logsanitizer.sqlite3`; set `LOGSANITIZER_DATA_DIR` to select a
different local data directory. On POSIX systems the application attempts to
restrict the directory to owner-only access and the database file to owner
read/write access. Filesystem permission behavior may vary by platform.

Available endpoints:

- `GET /api/projects` — list projects.
- `POST /api/projects` — create a project with `name` and optional `description`.
- `GET /api/projects/{id}` — retrieve one project.

Creating a project does not import or process files. Project deletion, file import,
sanitization, mapping storage, authentication, and release controls are not yet
implemented. This scaffold is not approved for real/sensitive logs and must not
be exposed to a network.

Run tests with `pytest` and lint with `ruff check src tests`.
