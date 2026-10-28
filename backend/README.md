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
schema is versioned and upgrades older installations to version 3, adding persisted detected-format and manual-override fields.
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
does not read or copy file contents, modify originals, or start sanitization. The
response includes a `format_hint` inferred only from the filename extension (`json`,
`jsonl`, `text`, `xml`, `csv`, or `unknown`). This is not content validation; an
unknown extension stays `unknown`, and the hint must not be treated as proof of the
actual format. Format detection is a separate explicit action (`POST /api/projects/{id}/files/{file_id}/detect-format`): it samples at most 64 KiB locally and returns only a classification, not source content. Uncertain or binary samples remain `unknown`. The detected classification is persisted in SQLite. A separate `PUT /api/projects/{id}/files/{file_id}/format` endpoint stores a manual override from `text`, `json`, `jsonl`, `xml`, `csv`, or `unknown`; sending `null` clears the override. The override is stored separately from the detected classification. Detection remains heuristic, is not full-file validation, and is not approval. A graphical folder picker is not implemented yet.

This scaffold is not approved for real/sensitive logs and must not be exposed to
a network: authentication, authorization, processing, mapping protection, and
release controls are still missing.

Run tests with `pytest` and lint with `ruff check src tests`.


## Lokale Anmeldung und Rollen

Vor dem ersten Start einen Administrator interaktiv anlegen:

```bash
python -m logsanitizer.auth_cli
```

Das Kommando fragt Benutzername und Passwort verdeckt ab. Es gibt keinen öffentlichen Bootstrap-Endpunkt und kein eingebautes Standardpasswort. Passwörter werden mit scrypt gehasht; Sitzungen verwenden zufällige opaque Tokens, deren SHA-256-Digests gespeichert werden. Sitzungen laufen nach acht Stunden ab. Benutzer können mehrere Rollen erhalten: `admin`, `operator`, `reviewer` und `approver`. Benutzerverwaltung ist Administratoren vorbehalten. Änderungen an API-Daten benötigen zusätzlich den CSRF-Header `X-CSRF-Token`, passend zum `logsanitizer_csrf`-Cookie.

Für HTTPS-Bereitstellungen `LOGSANITIZER_COOKIE_SECURE=1` setzen. Bei lokalem HTTP ist das Secure-Attribut standardmäßig aus; die Anwendung sollte dann nur an Loopback gebunden sein. Die derzeitige Rollenmatrix ist eine Grundlage und muss vor Netzwerkbetrieb weitergehend geprüft werden. Es gibt noch keine Passwortwiederherstellung, keine Administrationsoberfläche für Benutzer und keine Begrenzung wiederholter fehlgeschlagener Anmeldungen. Authentifizierung allein macht die Anwendung noch nicht produktionsreif.
