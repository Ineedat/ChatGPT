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

The current development scaffold includes local SQLite project management, source-file registration, heuristic format detection on a sample of at most 64 KiB, manual per-file format selection, and explicit full-file format validation for text, JSON, JSON Lines, CSV, and XML. It also includes a versioned JSON rule-configuration schema (v1), shared rules and source-specific profiles, plain-text/regex match definitions, case sensitivity, priorities, regex syntax checks, exact-priority conflict detection, and local atomic persistence through the API. These rules are configuration only and are not yet applied to log contents. Validation reports format/syntax errors and byte counts without returning source content. Detection is only a guess based on a bounded sample; full-file syntax validation is not a sanitization scan and does not prove that sensitive values have been found. The rule execution engine, sanitization streaming pipeline, persistent mapping store, authentication, review workflow, and packaging remain planned work.

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
