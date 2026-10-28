# Security review — development branch

**Review date:** 2026-10-28  
**Scope:** Static review of the current development branch, focusing on authentication, authorization, local file handling, regex execution, sensitive mapping storage, and release posture. This is not a penetration test or a production approval.

## Changes made during this review

- Login attempts are throttled per normalized username and direct client address: five failed attempts in a five-minute window trigger a five-minute lock. The key is hashed; stale throttle records are pruned.
- The API documentation and OpenAPI schema now pass through authentication middleware instead of being public. The health endpoint and login endpoint remain public by design.
- Regression tests cover lockout behavior and unauthenticated access to the docs/schema.

These controls reduce risk but do not establish production readiness. Verify the CI run for the current commit before relying on the changes.

## Findings still open

### LS-SEC-001 — Original-value mappings are stored in plaintext

- **Severity:** High
- **Location:** `backend/src/logsanitizer/mapping_store.py`, `get_or_create_indexed_mapping`
- **Evidence:** The `indexed_mappings.original_value` column stores each original matched value. File permissions are restricted where the platform supports POSIX modes, but the database itself is not encrypted.
- **Impact:** Anyone who obtains a copy of the mapping database or runs under the same OS account can recover values that sanitization replaced, potentially including identifiers or secrets.
- **Required fix:** Design and implement encryption at rest with an explicit local key-provisioning and recovery model. Do not hard-code or commit a key. Document what happens if the key is lost, rotated, or unavailable offline.
- **Release gate:** Do not use real confidential logs until this is addressed and tested on Windows and Linux.

### LS-SEC-002 — User-configured regular expressions have no execution timeout

- **Severity:** High
- **Location:** `backend/src/logsanitizer/rule_config.py`, regex validation; `backend/src/logsanitizer/sanitizer.py`, rule compilation, substitution, and residual scanning
- **Evidence:** Patterns are compiled with Python's standard `re` engine and executed against input lines without a time budget. The line-size cap limits each line to 1 MiB but does not prevent catastrophic backtracking.
- **Impact:** A pathological rule and crafted input can consume excessive CPU and stall a sanitization worker, including during the mandatory residual scan.
- **Required fix:** Use a regex engine with enforceable timeouts, or a conservative supported-pattern subset with rejection of risky constructs and tests. Keep limits on pattern length, input line length, and concurrent jobs. A heuristic alone must not be represented as a complete defense.
- **Release gate:** Do not permit untrusted users to import/edit regex rules on a network-accessible instance until a timeout or equivalent robust control exists.

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
