# Security review — development branch

**Review date:** 2026-10-28  
**Scope:** Static review of the current development branch, focusing on authentication, authorization, local file handling, regex execution, sensitive mapping storage, and release posture. This is not a penetration test or a production approval.

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
- **Required fix:** Introduce a configured output workspace and validate resolved destinations against it; define explicit import/export locations and permissions. Preserve no-overwrite and symlink protections, including against races.
- **Release gate:** Complete controlled output/release workflow before production use.

### LS-SEC-004 — Secure-cookie behavior is opt-in

- **Severity:** Medium
- **Location:** `backend/src/logsanitizer/auth.py`, login cookie configuration
- **Evidence:** The `Secure` cookie attribute is enabled only when `LOGSANITIZER_COOKIE_SECURE` is set to a truthy value.
- **Impact:** If the service is exposed over plain HTTP on a network, a session cookie could be transmitted without transport encryption. SameSite and HttpOnly do not encrypt traffic.
- **Required fix:** Keep loopback-only HTTP as the safe default; require explicit secure deployment configuration for non-loopback binding, and document HTTPS termination and trusted-proxy assumptions. Do not enable network mode until that behavior is enforced and tested.

### LS-SEC-005 — Authentication and role enforcement need broader integration testing

- **Severity:** Medium
- **Location:** `backend/src/logsanitizer/auth.py`, `AuthMiddleware`; route handlers in `backend/src/logsanitizer/main.py` and `review_workflow.py`
- **Evidence:** Authorization is implemented with path/method checks in middleware plus per-handler ownership checks. Existing tests cover key login, CSRF, role, review, and output-integrity cases, but the full route/role matrix and hostile path variants have not been exhaustively verified.
- **Impact:** A future route or path variation could accidentally bypass a role boundary, or disclose project/review metadata to an unintended role.
- **Required fix:** Add a table-driven authorization test for every API route and each role, including unauthenticated access, CSRF on every state-changing route, ownership boundaries, and route normalization/encoded path variants. Prefer explicit route-level dependencies or router-level deny-by-default policies over relying only on substring/prefix matching.

## Additional release blockers (not a complete security finding list)

- No comprehensive sensitive-data detection; residual scanning only checks configured rules.
- No verified 5 GB performance/integration test or large-file resource budget.
- No Windows/Linux portable packaging and installation-hardening verification.
- No controlled, auditable release/export workflow.
- SMTP delivery is best-effort and has no persistent retry queue.
- CI tests are not a substitute for security testing on supported operating systems and realistic data.

## Exit criteria before network or confidential-data use

1. Close LS-SEC-001 and LS-SEC-002 with regression tests.
2. Close or explicitly accept LS-SEC-003 and LS-SEC-004 with enforced deployment safeguards.
3. Complete the route/role authorization matrix and independent security review.
4. Verify large-file behavior, dependency advisories, Windows/Linux file permissions, and packaging in isolated test environments.
5. Keep the application loopback-only until all applicable gates are closed.
