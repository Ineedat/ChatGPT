# LogSanitizer

Portable, offline-first application for sanitizing application logs on Windows and Linux.

> **Project status:** Active development. The current branch contains a development implementation; not all planned formats, large-file performance targets, or deployment scenarios have been fully verified.

## Product direction — requirements v2.8

LogSanitizer runs only on a standalone laptop or inside a defined, internet-disconnected Air-Gap network. It is not intended for public or untrusted networks. The product is deliberately not a high-security platform: prioritize **performance, low resource consumption, ease of use and maintainability** over elaborate local encryption, key custody, filesystem ACL engineering or mandatory output-path restrictions.

The user and workflow model remains important: administrator, Rule Owner, Processor and Reviewer/Releaser roles; review queue; approval/return/stop; run history and audit trail.

## Goals

- Stream large log files (target: at least 5 GB) without loading whole files into memory.
- Keep source files unchanged.
- Apply configurable rules to text logs and structured formats.
- Keep placeholder mappings consistent across all files in a project.
- Work fully offline, including documentation and UI assets.
- Provide clear progress, cancellation, validation and review workflows.
- Offer a simple portable Windows/Linux deployment for standalone and defined Air-Gap operation.

## Deployment

**Standalone:** local account, loopback binding, local data.

**Air-Gap network:** explicitly configured interface and network profile; optional LDAP/Active Directory role mapping and SMTP review notifications. Network operation is limited to the defined isolated network. No cloud or internet dependency.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and the example deployment configuration.

## Technology

- Backend: Python 3.11+ and FastAPI
- Frontend: React and TypeScript
- Metadata and local mappings: SQLite
- Configuration: versioned JSON
- Tests: pytest and frontend test tooling

## Functional scope

The development branch includes project and source-file registration, heuristic format detection, manual format selection, format validation, versioned rule configuration, shared rules and source profiles, streaming text/JSONL processing, project-scoped indexed placeholders, cancellable background jobs, persistent run history, local accounts, role checks and the review workflow.

The current implementation still contains some high-security mechanisms from the previous requirements baseline (including encrypted mapping storage and enforced output-workspace checks). These are transitional implementation details, not requirements under v2.8; they are scheduled for simplification. Do not assume that the implementation has already been simplified merely because the requirements changed.

Not all formats are supported by the sanitization engine yet. Comprehensive sensitive-data detection and measured 5-GB performance are also outstanding. A validation scan only checks configured rules and format integrity; it does not prove that every sensitive value has been detected.

## Requirements and roadmap

- [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) — current baseline **v2.8**
- [docs/ROADMAP.md](docs/ROADMAP.md) — implementation milestones
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — architecture decisions

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

Keep local development bound to 127.0.0.1. Only configure a network bind for the defined Air-Gap deployment.

## Operating principles

- Never commit real log files, credentials, tokens, local databases, generated outputs or user data.
- Source files are read-only inputs and must not be modified or deleted by the application.
- Failed or incomplete runs must not be marked successful or approved.
- User roles, reviewer decisions and audit history remain part of the product.
- No runtime internet access, cloud service or external asset dependency.

## License

No license has been selected yet. All rights reserved by default until a license is explicitly chosen.
