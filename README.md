# LogSanitizer

A portable, offline-first application for sanitizing application log files on Windows and Linux.

> **Project status:** Early development scaffold. This repository does not yet provide a production-ready sanitization workflow. Do not use it to release real or sensitive logs until the security and validation requirements are implemented and tested.

## Goals

- Process large log files (target: at least 5 GB) using streaming, without loading whole files into memory.
- Leave source files unchanged.
- Apply configurable, testable sanitization rules to text logs and structured JSON.
- Keep placeholder mappings consistent across all files in a project.
- Work fully offline, including documentation and UI assets.
- Support review, validation, audit, and controlled release workflows.

## Technology

- Backend: Python 3.11+ and FastAPI
- Frontend: React and TypeScript
- Metadata: SQLite
- Configuration: versioned JSON
- Tests: pytest and frontend test tooling

## Current scope

The initial milestone establishes the project structure, API health endpoint, frontend shell, and development instructions. The rule engine, streaming pipeline, persistent mapping store, authentication, review workflow, and packaging are planned work and must not be considered implemented until documented and tested.

## Requirements

See [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) for the current requirements baseline (v2.7) and [docs/ROADMAP.md](docs/ROADMAP.md) for milestones.

## Development

Backend:

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn logsanitizer.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Keep the backend bound to `127.0.0.1` during development. Do not expose it to a network until authentication, authorization, secure configuration, and network-binding safeguards have been implemented and reviewed.

## Security principles

- Never upload log contents, secrets, or mapping data to this repository.
- Never commit real log files, credentials, tokens, local databases, generated outputs, or user data.
- Source files are read-only inputs and must not be modified or deleted by the application.
- A successful validation scan is not proof that every sensitive value has been detected.
- Incomplete or failed runs must never be treated as releasable output.

## License

No license has been selected yet. All rights reserved by default until a license is explicitly chosen.
