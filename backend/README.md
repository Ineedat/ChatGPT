# Backend

Das Backend verwendet Python 3.11+, FastAPI und SQLite. Die vollständige Betriebs- und Konfigurationsreferenz steht in [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md). Sie ist Teil der Offline-Dokumentation des portablen Pakets.

## Entwicklung starten

Im Verzeichnis `backend`:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# Linux:
source .venv/bin/activate

python -m pip install -e ".[dev,ldap]"
python -m logsanitizer
```

Die LDAP-Abhängigkeit ist optional. Ohne LDAP kann für lokale Entwicklung auch `python -m pip install -e ".[dev]"` verwendet werden.

Standardmäßig ist die lokale Oberfläche unter `http://127.0.0.1:8000` erreichbar. Health Check: `/api/health`. Die API-Dokumentation unter `/api/docs` ist erst nach Anmeldung erreichbar.

## Deployment-Konfiguration

Kopieren Sie `config/deployment.example.json` nach `config/deployment.json`. Alternativ kann `LOGSANITIZER_CONFIG` auf eine externe Konfigurationsdatei zeigen. Relative Pfade werden relativ zum Speicherort der JSON-Datei aufgelöst.

Die beiden Betriebsprofile:

- **Standalone:** `profile=standalone`, `server.bind_host=127.0.0.1`, `auth.provider=local`. LDAP und SMTP bleiben deaktiviert.
- **Air-Gap-Netzwerk:** `profile=network`, konkrete interne Bind-Adresse, HTTPS-Zertifikat und privater Schlüssel. Anmeldung wahlweise lokal oder mit `auth.provider=ldap`. LDAP erfordert `ldap.enabled=true` und LDAPS oder StartTLS.

### LDAP-Benutzername und Passwort

Bei `auth.provider=ldap` melden sich Anwender auf der normalen Loginseite mit ihrem persönlichen LDAP-/Active-Directory-Benutzernamen und ihrem persönlichen Verzeichnispasswort an. Das Passwortfeld ist nicht auf lokale Konten beschränkt. Ein persönliches Client-Zertifikat ist für diese Passwortanmeldung nicht erforderlich.

Das technische Suchkonto wird getrennt konfiguriert: `ldap.bind_dn` ist dessen DN und `LOGSANITIZER_LDAP_BIND_PASSWORD` dessen Passwort. Das Suchkonto findet den Benutzer und liest Gruppenattribute. Danach authentifiziert das Backend den gefundenen Benutzer-DN separat mit dem Passwort aus dem Loginformular. Das Dienstkonto-Passwort ist also ausdrücklich nicht das Passwort des angemeldeten Mitarbeiters.

Für die LDAP-Verbindung müssen LDAPS oder StartTLS aktiviert sein. `ldap.ca_certs_file` verweist bei Bedarf auf eine CA-Datei zur Prüfung des LDAP-Serverzertifikats; es ist kein persönliches Benutzerzertifikat. `server.tls_certfile` und `server.tls_keyfile` gehören dagegen zum HTTPS-Webserver von LogSanitizer.

### Geheimnisse

Passwörter gehören niemals in `deployment.json`. Unterstützte Prozessumgebungsvariablen:

- `LOGSANITIZER_LDAP_BIND_PASSWORD`: Passwort des technischen LDAP-Suchkontos.
- `LOGSANITIZER_SMTP_USERNAME` und `LOGSANITIZER_SMTP_PASSWORD`: optionale SMTP-Anmeldung; beide gemeinsam setzen.
- `LOGSANITIZER_CONFIG`: optionaler Pfad zur Deployment-Konfiguration.
- `LOGSANITIZER_DATA_DIR`: optionaler Datenverzeichnis-Override.

Die Umgebungsvariablen müssen vor dem Start im Prozesskontext gesetzt sein. Für Windows- und Linux-Dienste sind die jeweiligen Dienstmanager bzw. lokal geschützte Environment-Dateien zu verwenden. Keine Geheimnisse in Git, Kommandozeilenargumente oder Logs schreiben.

## Ersten lokalen Administrator anlegen

Bei lokaler Anmeldung den ersten Administrator interaktiv anlegen:

```bash
python -m logsanitizer.auth_cli
```

Das Kommando fragt das Passwort verdeckt ab. Im LDAP-Modus werden Benutzer und Rollen aus dem Verzeichnis bezogen; ein lokaler Passwort-Fallback findet nicht statt.

## Tests und Qualität

```bash
pytest
ruff check src tests
```

Die automatisierten LDAP-Tests simulieren den Verzeichnisserver. Die echte LDAP-/AD-, TLS- und SMTP-Integration muss zusätzlich in der vorgesehenen Air-Gap-Umgebung abgenommen werden.
