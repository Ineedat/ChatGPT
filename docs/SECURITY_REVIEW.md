# Security review — development branch

**Review date:** 2026-10-28  
**Scope:** Static review of the current development branch, focusing on authentication, authorization, local file handling, regex execution, sensitive mapping storage, deployment profiles, LDAP/TLS, and portable build readiness. This is not a penetration test or a production approval.

## Changes made during this review

- Login attempts are throttled per normalized username and direct client address: five failed attempts in a five-minute window trigger a five-minute lock. The key is hashed; stale throttle records are pruned.
- The API documentation and OpenAPI schema now pass through authentication middleware instead of being public. The health endpoint and login endpoint remain public by design.
- Regex substitutions and residual scans now use the timeout-capable `regex` engine with a 100 ms per-operation limit; timeout failures reject the run and remove partial output.
- Regression tests cover lockout behavior, unauthenticated access to the docs/schema, and pathological regex timeout cleanup.

These controls reduce risk but do not establish production readiness. Verify the CI run for the current commit before relying on the changes.

## Findings still open

### LS-SEC-001 — Original-value mapping encryption

- **Status:** Implemented; automated CI passed on Linux and Windows mapping-specific tests. This is not a penetration test or independent verification on every supported Windows/Linux release.
- **Location:** `backend/src/logsanitizer/mapping_store.py`.
- **Change:** Original values are encrypted with AES-256-GCM. A separate 32-byte random key file is created locally; HKDF-SHA-256 derives distinct encryption and keyed-lookup keys. A keyed HMAC fingerprint preserves stable lookup without storing the source value in plaintext. POSIX data-directory permissions are set to `0700` and key-file permissions to `0600`; on Windows the application removes inherited ACLs and grants the current user access to the mapping data directory and key file, failing closed if ACL application fails. Windows ACL checks are exercised in CI. A key-check record prevents silently using a wrong replacement key. Missing keys for an already encrypted database fail closed.
- **Migration:** Existing plaintext mappings are migrated on first use, the old table is dropped, and SQLite `VACUUM` is run to compact the database. This cannot guarantee erasure of SSD blocks, filesystem snapshots, or old backups.
- **Backup limitation:** Database and key must be backed up together for recovery. Anyone who obtains both can recover mappings; protect the key separately and keep a secure offline recovery copy. Losing the key makes mapping recovery impossible.
- **Residual release gate:** Perform a documented restore drill on the actual target Windows/Linux versions and review key custody, backups, and filesystem/SSD remnants before confidential-data use.

### LS-SEC-002 — User-configured regex execution timeout

- **Status:** Mitigated in the current branch; regression-tested, pending final CI confirmation.
- **Location:** `backend/src/logsanitizer/sanitizer.py`, rule substitution and residual scanning.
- **Change:** Runtime execution now uses the `regex` package with a 100 ms timeout for each substitution/search operation. A timeout raises a sanitization error, and partial output is removed. A pathological-pattern regression test exercises this behavior.
- **Residual caution:** This is a per-operation limit, not a global job deadline or concurrency limit. Keep pattern/input limits and add a global resource budget before network deployment.

### LS-SEC-003 — Output destination is selected as an arbitrary absolute path

- **Severity:** Medium
- **Location:** `backend/src/logsanitizer/main.py`, sanitization request handling; `backend/src/logsanitizer/sanitizer.py`, staging and publication
- **Evidence:** The request accepts an absolute `output_path`; the worker creates a staging file in that destination's parent directory. Existing targets and final-component symlinks are rejected, but there is no configured workspace allowlist.
- **Impact:** An authenticated operator can ask the service to create a new file in any directory writable by the service account. This increases accidental disclosure and path-confusion risk.
- **Status (2026-10-29):** Partially mitigated in the development branch. A configurable `output_workspace` is resolved relative to the deployment JSON (default: `data_dir/outputs`). Both synchronous and background API routes reject destinations outside it, path traversal, symlinked workspace/parent components, missing target directories, and existing targets. The sanitizer repeats the workspace check immediately before staging/publication. Regression tests cover outside-workspace requests, traversal, and symlinked directories.
- **Remaining gap:** This is not yet race-resistant against a hostile concurrent local process replacing directory entries between validation and file creation/publication. The current path-based staging and hard-link publication still require OS-level directory-handle / reparse-point-safe handling on Linux and Windows. Do not mark this finding closed.
- **Required fix:** Complete race-resistant publication on both supported operating systems, test parent-directory replacement and final-component races, and define explicit import/export locations and permissions.
- **Release gate:** Complete controlled output/release workflow and the race-hardening tests before production use.

### LS-SEC-004 — Network transport and secure-cookie configuration

- **Status:** Mitigated in the current branch; CI and target-environment verification pending.
- **Location:** `backend/src/logsanitizer/deployment.py`, `backend/src/logsanitizer/__main__.py`, `backend/src/logsanitizer/auth.py`.
- **Change:** Standalone mode rejects non-loopback binds. Network mode requires LDAP, a configured network bind, existing TLS certificate/key files, and an LDAP service secret; the launcher starts Uvicorn with HTTPS and the login route sets Secure cookies. LDAP requires LDAPS or StartTLS and validates the server certificate and hostname. SMTP in network configuration must use STARTTLS or SSL.
- **Residual caution:** The configuration can verify the presence of TLS files but cannot establish that a certificate is issued by the expected organization or that firewall rules are correct. Verify the actual certificate, service-account permissions, interface exposure, and real LDAP/SMTP integration before production use.

### LS-SEC-005 — Authentication and role enforcement need broader integration testing

- **Severity:** Medium
- **Location:** `backend/src/logsanitizer/auth.py`, `AuthMiddleware`; route handlers in `backend/src/logsanitizer/main.py` and `review_workflow.py`
- **Evidence:** Authorization is implemented with path/method checks in middleware plus per-handler ownership checks. Existing tests cover key login, CSRF, role, review, and output-integrity cases, but the full route/role matrix and hostile path variants have not been exhaustively verified.
- **Impact:** A future route or path variation could accidentally bypass a role boundary, or disclose project/review metadata to an unintended role.
- **Required fix:** Add a table-driven authorization test for every API route and each role, including unauthenticated access, CSRF on every state-changing route, ownership boundaries, and route normalization/encoded path variants. Prefer explicit route-level dependencies or router-level deny-by-default policies over relying only on substring/prefix matching.

## Additional release blockers (not a complete security finding list)

- No comprehensive sensitive-data detection; residual scanning only checks configured rules.
- No verified 5 GB performance/integration test or large-file resource budget.
- A PyInstaller one-folder build specification and Windows/Linux CI build/smoke-test job have been added; successful artifact builds and installation-hardening verification are still release gates.
- No controlled, auditable release/export workflow.
- SMTP delivery is best-effort and has no persistent retry queue.
- CI tests are not a substitute for security testing on supported operating systems and realistic data.

## Exit criteria before network or confidential-data use

1. Keep LS-SEC-001 and LS-SEC-002 regression-tested and complete a documented restore drill.
2. Close or explicitly accept LS-SEC-003 and LS-SEC-004 with enforced deployment safeguards.
3. Complete the route/role authorization matrix and independent security review.
4. Verify large-file behavior, dependency advisories, Windows/Linux file permissions, and packaging in isolated test environments.
5. Keep the application loopback-only until all applicable gates are closed.
