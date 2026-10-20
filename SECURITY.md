# Security policy

## Status
LogSanitizer is an early-development scaffold, not a security-reviewed product. Do not use it to release real sensitive logs.

## Reporting
Report suspected vulnerabilities privately to the repository owner. Do not create issues containing secrets, log excerpts, credentials, mapping tables, or personal data.

## Principles
- Keep processing local and bind to loopback during development.
- Never commit real logs, credentials, tokens, mappings, databases, or generated outputs.
- Do not include sensitive content in diagnostics or audit metadata.
- Preserve source files and block incomplete or failed outputs from release.
- A successful validation scan does not prove every sensitive value was detected.
