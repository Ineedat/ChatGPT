# Backend

From this directory:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m logsanitizer
```

Health check: `http://127.0.0.1:8000/api/health`. API docs: `http://127.0.0.1:8000/api/docs` (after login).\n\n## Deployment profiles (portable Windows/Linux)\n\nCopy `config/deployment.example.json` to `config/deployment.json` or set `LOGSANITIZER_CONFIG` to an external JSON file. The local configuration file is ignored by Git. `data_dir` can be set to a path relative to the configuration file (for example `./data`) so the database and mapping key travel with a portable folder; leave it empty to use the user data directory. Ensure the portable data directory is writable and protected. The same config layout is intended to ship beside a portable build; never put passwords or secrets in the JSON file. Supply secrets through process environment variables.\n\n### Standalone laptop / offline\n\nUse `profile: standalone`, `server.bind_host: 127.0.0.1`, and `auth.provider: local`. The app rejects non-loopback binds in this profile and disables SMTP. No LDAP connection or LDAP dependency is needed. Start from the backend directory with `python -m logsanitizer`. Create the initial local administrator with `python -m logsanitizer.auth_cli`.\n\n### Network / Darksite\n\nUse `profile: network`, set `server.bind_host` to the explicit interface address, `server.tls_certfile and server.tls_keyfile pointing to valid TLS certificate/private-key files`, and `auth.provider: ldap`. Network mode refuses to start unless LDAP is enabled, its host/bind DN/search base and explicit role-group mapping are set, and `LOGSANITIZER_LDAP_BIND_PASSWORD` is provided. Install the optional dependency with `python -m pip install -e ".[ldap]"`. LDAPS or StartTLS is mandatory; unencrypted LDAP is rejected. Direct LDAP group membership is mapped to `admin`, `operator`, `reviewer`, and `approver`. Local-password login is not used as a fallback in network mode.\n\nIf SMTP is enabled in the network profile, configure its host, port, `security` (`starttls` or `ssl` preferred), sender, reviewer/operator recipient lists in JSON. SMTP credentials, if needed, must be supplied as `LOGSANITIZER_SMTP_USERNAME` and `LOGSANITIZER_SMTP_PASSWORD`; the configured network SMTP transport must use STARTTLS or SSL. LDAP service credentials use `LOGSANITIZER_LDAP_BIND_PASSWORD`. The launcher serves HTTPS directly in network mode and sets session cookies Secure. Relative certificate paths are resolved against the deployment JSON file. Protect the private-key file with OS-level permissions and install a certificate trusted by client systems. Do not expose the development server directly to untrusted networks.\n\n`config/deployment.example.json` uses reserved example domains and is not ready to connect to a real directory or mail server. A real network deployment still requires a security review and integration test against the organization’s LDAP/AD and SMTP infrastructure.

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

## Verschlüsselung der Mapping-Datenbank

Die Mapping-Datenbank speichert Originalwerte nicht mehr im Klartext. Die Anwendung verwendet AES-256-GCM für die Originalwerte, einen separaten HMAC-basierten Suchfingerabdruck zur Wiedererkennung und eine lokale Schlüsseldatei:

- Datenbank: `mappings.sqlite3`
- Schlüssel: `mappings.key` im selben Datenverzeichnis (32 zufällige Bytes)
- Schlüsselableitung: HKDF-SHA-256 trennt Verschlüsselungs- und Suchschlüssel; der Schlüssel wird nicht in Git oder der Datenbank gespeichert.
- POSIX: Datenverzeichnis Modus `0700`, Schlüsseldatei `0600`; Windows: die Anwendung entfernt die ACL-Vererbung und beschränkt das Mapping-Datenverzeichnis sowie die Schlüsseldatei auf den aktuellen Benutzer. Kann Windows die ACL nicht setzen, bricht die Initialisierung ab. Die CI prüft Mapping-Verschlüsselung, Recovery und Windows-ACLs auf einem Windows-Runner; die vollständige Backend-Suite läuft unter Linux.
- Beim ersten Start wird der Schlüssel lokal erzeugt. Fehlt er später bei einer bereits verschlüsselten Datenbank oder passt er nicht, startet die Mapping-Verarbeitung nicht mit einem Ersatzschlüssel.
- Ältere Mapping-Datenbanken mit Klartextwerten werden beim ersten Zugriff migriert. Die Anwendung verschlüsselt die Werte, entfernt die alte Tabelle und führt `VACUUM` aus, um zurückgebliebene Seiten nach Möglichkeit zu bereinigen.

**Backup und Wiederherstellung:** Datenbank und Schlüssel müssen gemeinsam und unverändert gesichert werden. Ein Backup nur der Datenbank kann nicht entschlüsselt werden; ein verlorener oder beschädigter Schlüssel bedeutet Verlust der Zuordnung. Wer Datenbank und Schlüssel zusammen erhält, kann die Werte weiterhin entschlüsseln. Die Schlüsseldatei ist daher getrennt von normalen Backups der Datenbank zu schützen; bewahre eine geschützte Wiederherstellungskopie offline auf. Sichere Löschung alter Klartext-Backups oder physischer SSD-Blöcke kann die Anwendung nicht garantieren. Die Migration kann solche alten Kopien nicht nachträglich verschlüsseln.

Dies ist Verschlüsselung auf Anwendungsebene für die Mapping-Werte, keine vollständige Verschlüsselung aller SQLite-Metadaten oder des gesamten Datenträgers. Für zusätzlichen Schutz gegen Geräteverlust wird weiterhin vollständige Datenträgerverschlüsselung empfohlen. Die Schlüsseldatei liegt standardmäßig neben der Datenbank, sodass Dateiberechtigungen und Backup-Verfahren Teil des Sicherheitsmodells sind.

This scaffold is not approved for real/sensitive logs or network exposure. Local authentication and basic role checks are implemented but still require full security verification. Mapping-value encryption with a separate local key file is implemented in this branch; Windows ACL and recovery behavior still require cross-platform verification. Comprehensive sensitive-data detection and release controls remain incomplete.

Run tests with `pytest` and lint with `ruff check src tests`.


## Lokale Anmeldung und Rollen

Vor dem ersten Start einen Administrator interaktiv anlegen:

```bash
python -m logsanitizer.auth_cli
```

Das Kommando fragt Benutzername und Passwort verdeckt ab. Es gibt keinen öffentlichen Bootstrap-Endpunkt und kein eingebautes Standardpasswort. Passwörter werden mit scrypt gehasht; Sitzungen verwenden zufällige opaque Tokens, deren SHA-256-Digests gespeichert werden. Sitzungen laufen nach acht Stunden ab. Benutzer können mehrere Rollen erhalten: `admin`, `operator`, `reviewer` und `approver`. Benutzerverwaltung ist Administratoren vorbehalten. Änderungen an API-Daten benötigen zusätzlich den CSRF-Header `X-CSRF-Token`, passend zum `logsanitizer_csrf`-Cookie.

Für HTTPS-Bereitstellungen `LOGSANITIZER_COOKIE_SECURE=1` setzen. Bei lokalem HTTP ist das Secure-Attribut standardmäßig aus; die Anwendung sollte dann nur an Loopback gebunden sein. Die derzeitige Rollenmatrix ist eine Grundlage und muss vor Netzwerkbetrieb weitergehend geprüft werden. Es gibt noch keinen Selbstbedienungsprozess für Passwortänderung oder -wiederherstellung, keine Administrationsoberfläche für Benutzer und keine Begrenzung wiederholter fehlgeschlagener Anmeldungen. Authentifizierung allein macht die Anwendung noch nicht produktionsreif.
\n\n## Prüf- und Freigabeprozess\n\nDie Prüfhistorie und Audit-Ereignisse werden in `review.sqlite3` im konfigurierten lokalen Datenverzeichnis gespeichert; Quell- und Ausgabeinhalte werden nicht in diese Datenbank kopiert. Erfolgreich validierte Läufe werden manuell zur Prüfung gestellt, wenn mindestens ein aktivierter Benutzer `reviewer` oder `approver` besitzt. Ohne diese Rollen erfolgt eine automatische Freigabe nur nach bestandener Pflichtvalidierung.\n\n- `GET /api/reviews/queue` — ausstehende Prüfungen (Rollen `reviewer`, `approver` oder `admin`).\n- `GET /api/reviews/runs` — dauerhafte Laufhistorie und Statusfilter.\n- `GET /api/reviews/runs/{run_id}/search?q=...` — wörtliche Suche ausschließlich in der bereinigten Ausgabe; maximal 20 Treffer und 300 Zeichen je Treffer.\n- `GET/POST /api/reviews/saved-searches` — persönliche Suchmuster; fremde Suchmuster sind nicht zugänglich.\n- `POST /api/reviews/runs/{run_id}/approve`, `/return`, `/stop` — Prüfentscheidung; eine Ausnahmefreigabe erfordert eine ausdrückliche Begründung.\n- `POST /api/reviews/runs/{run_id}/comments` — Kommentar protokollieren.\n- `GET /api/reviews/audit` — Audit-Ereignisse; Ereignisse sind über die Anwendungsdatenbank nicht änder- oder löschbar.\n\nFehlgeschlagene Sanitisierung oder Pflichtvalidierung erzeugt keinen freigabefähigen Lauf. Rückgegebene Läufe können mit `retry_of_run_id` erneut bereinigt und als neuer Lauf mit Bezug auf den Vorgänger gespeichert werden. Die Suchfunktion untersucht nie die Originaldatei. Review-Metadaten enthalten keine absoluten Ausgabe- oder Quellpfade in API-Antworten.\n\nHintergrundjob-Status und Fortschritt werden in `sanitize_jobs.sqlite3` im lokalen Datenverzeichnis persistiert. Beim Start werden Läufe, deren Worker-Prozess nicht mehr existiert, als `interrupted` markiert; passende Staging-Dateien werden bereinigt, sofern kein aktiver Lauf dieselbe Ausgabe beansprucht. Der Status-Endpunkt stellt den gespeicherten Fortschritt nach einem Neustart wieder her. Unterbrochene Läufe werden nicht automatisch fortgesetzt; der Bediener muss einen neuen Lauf starten. Optionale SMTP-Benachrichtigungen werden über Umgebungsvariablen konfiguriert. `LOGSANITIZER_SMTP_HOST`, `LOGSANITIZER_SMTP_PORT` (Standard 587), `LOGSANITIZER_SMTP_FROM` und `LOGSANITIZER_SMTP_SECURITY` (`starttls`, `ssl` oder `none`) steuern den Transport. Optional sind `LOGSANITIZER_SMTP_USERNAME` und `LOGSANITIZER_SMTP_PASSWORD`; beide müssen zusammen gesetzt sein. `LOGSANITIZER_REVIEWER_EMAILS` ist eine kommaseparierte Empfängerliste für neue Prüffälle, `LOGSANITIZER_OPERATOR_EMAILS` für zurückgegebene Läufe. Ohne SMTP-Host/Absender oder Empfänger bleibt Versand deaktiviert. E-Mails enthalten nur Lauf-ID und Dateianzeigename, keine Loginhalte, Kommentare oder absoluten Pfade. Versandfehler blockieren die Bereinigung/Freigabe nicht; fehlgeschlagene E-Mails werden derzeit nicht automatisch erneut versendet. Vor Netzwerkbetrieb ist weiterhin eine vollständige Sicherheitsprüfung erforderlich.\n