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

## Local metadata and source registration

The SQLite database stores project and source-file metadata, not log contents.
By default it is `~/.logsanitizer/logsanitizer.sqlite3`; set
`LOGSANITIZER_DATA_DIR` to select another local data directory. The database
schema is versioned and upgrades the previous project-only schema to version 2.
On POSIX systems, the application attempts owner-only directory and database
permissions; filesystem behavior may vary by platform.

Available endpoints:

- `GET /api/projects` — list projects.
- `POST /api/projects` — create a project with `name` and optional `description`.
- `GET /api/projects/{id}` — retrieve one project.
- `GET /api/projects/{id}/files` — list registered source-file metadata.
- `POST /api/projects/{id}/files` — register a local source file using JSON
  `{"path": "/absolute/path/to/application.log"}`.

File registration checks that the project exists and the source path identifies
an existing regular file. Relative paths, directories, and final-component
symbolic links are rejected. Duplicate registration of the same canonical path
returns HTTP 409. The API returns only the display name, size, and timestamps;
it does not return the stored absolute path.

Folder registration is available at `POST /api/projects/{id}/files/import-folder`
with JSON `{"path": "/absolute/path/to/logs", "recursive": true}`. Recursive
import is enabled by default; set `recursive` to `false` to include only direct
children. The endpoint processes at most 5,000 candidate files per request,
skips symbolic links, reports duplicate/permission/other per-file failures, and
returns counts plus a per-file issue list. It registers file metadata only: it
does not read or copy file contents, modify originals, detect formats, or start
sanitization. A graphical folder picker is not implemented yet.

This scaffold is not approved for real/sensitive logs and must not be exposed to
a network: authentication, authorization, processing, mapping protection, and
release controls are still missing.

Run tests with `pytest` and lint with `ruff check src tests`.
