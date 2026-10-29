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

## Deployment profiles\n\nPortable Windows/Linux builds are designed to support two explicit profiles selected through a local JSON configuration file. **Standalone** is laptop-first: loopback-only binding, local accounts, no LDAP, and no SMTP. **Network/Darksite** requires an explicit interface binding, LDAP/Active Directory authentication with encrypted LDAP transport and explicit group-to-role mapping, HTTPS/TLS termination, and can use SMTP for review notifications. Service-account and SMTP passwords are environment secrets, never shipped in the portable config. See `config/deployment.example.json` and `backend/README.md`.\n\nThe deployment profile and launcher are implemented, but a packaged Windows/Linux release and a live integration test against a real LDAP/AD/SMTP environment are not yet complete. Network mode is not production-approved until the remaining security review is finished.\n\n## Technology\n
- Backend: Python 3.11+ and FastAPI
- Frontend: React and TypeScript
- Metadata: SQLite
- Configuration: versioned JSON
- Tests: pytest and frontend test tooling

## Current scope

The current development scaffold includes local SQLite project management, source-file registration, heuristic format detection on a sample of at most 64 KiB, manual per-file format selection, and explicit full-file format validation for text, JSON, JSON Lines, CSV, and XML. It also includes a versioned JSON rule-configuration schema (v1), shared rules and source-specific profiles, plain-text/regex match definitions, case sensitivity, priorities, regex syntax checks, exact-priority conflict detection, and local atomic persistence through the API. A first streaming execution endpoint now applies enabled shared rules and optional source-profile rules in ascending priority order to UTF-8 text and JSON Lines. It writes to a separate, non-existing destination, uses a 1 MiB maximum line size, removes partial output on processing or validation errors, and leaves the source unchanged. Before reporting success it re-reads the output as a bounded stream, validates UTF-8 and JSONL syntax where applicable, and scans all active shared/profile rule patterns for residual matches; a match blocks the run and deletes the output. The result explicitly reports `validated` and `validation_scope= configured_rules_and_format`. This scan only covers configured patterns and syntax; it does not prove that all sensitive data has been detected. Indexed replacement rules now support stable project-scoped placeholders such as `[IP_1]` across multiple files. Their original-value mappings are stored in a separate local SQLite database encrypted with AES-256-GCM; a separate 32-byte key file is protected with POSIX owner-only permissions or a Windows current-user ACL. Existing plaintext mappings are migrated on first access, but cross-platform security verification and backup/recovery procedures still require validation. Full JSON documents, XML, and CSV execution through the sanitization engine, controlled export/release, and comprehensive sensitive-data detection are not implemented. Sanitization can also run as a cancellable background job with byte/line progress. Output is staged in a private temporary file in the destination directory, validated before publication, and published without overwriting an existing target; the staging file is removed on normal success, failure, or cancellation. Job status and progress are persisted in `sanitize_jobs.sqlite3`; startup recovery marks jobs from dead worker processes as `interrupted` and safely removes matching orphaned staging files when no live job owns the output. Arbitrary user regexes can still have expensive execution behavior; this prototype is not production-ready. Validation reports format/syntax errors and byte counts without returning source content. Detection is only a guess based on a bounded sample; full-file syntax validation is not a sanitization scan and does not prove that sensitive values have been found. Basic local authentication and a persistent review workflow are now implemented in the development branch, including role-gated review, literal search of sanitized output only, per-user saved searches, approval/return/stop decisions, justified exceptions, and append-only audit events. The review history and background-job progress are durable in separate local SQLite databases. Interrupted jobs are marked `interrupted` at startup and are not automatically resumed; operators must revalidate the source and configuration by starting a new run. Full authentication/security verification and packaging remain open. Optional SMTP notifications are available through local environment configuration; delivery is best-effort and has no automatic retry queue.

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


## Local sign-in (development milestone)

Create the first local administrator from the backend directory with `python -m logsanitizer.auth_cli`. The interactive command prompts for a username and password and assigns the initial roles. No public bootstrap endpoint or default password is provided. Basic local authentication and role checks are implemented and tested, but a complete security review remains open; do not expose the app to a network or use real confidential logs until the remaining limitations are addressed. See `backend/README.md` for session, cookie, role, and configuration details.
\n\n## Review workflow (development status)\n\nThe **Prüfung & Verlauf** view shows the durable local run history. When at least one enabled account has the `reviewer` or `approver` role, successfully validated sanitization runs require a deliberate review decision. If neither role is assigned to any enabled account, a run is automatically approved only after all configured mandatory validation checks pass. Reviewer search uses literal terms against the sanitized output only and returns bounded snippets; original files are never searched or returned. Saved searches belong to the creating account. Approvals, returns, stops, comments, and explicit exception justifications are recorded in the local audit database. A returned run can be re-sanitized to a new destination while preserving a link to the previous run.\n\nThis is still a development prototype, not a production release. Review history and background-job progress survive restarts; jobs abandoned by a dead worker are marked `interrupted`, and matching staging files are cleaned up when safe. Jobs are not automatically resumed. Mapping encryption, comprehensive sensitive-data detection, a full security review, and Windows/Linux packaging remain outstanding. Optional SMTP notifications are configurable through local environment variables, with best-effort delivery and no automatic retry queue. Do not expose the service to a network or use real confidential logs until the remaining risks have been addressed.\n