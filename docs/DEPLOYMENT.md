# Deployment und portabler Betrieb

LogSanitizer ist für zwei klar abgegrenzte Betriebsarten vorgesehen: einen einzelnen Windows-/Linux-Laptop ohne Internetverbindung oder ein ausdrücklich definiertes, isoliertes Air-Gap-Netz. Ein Betrieb im öffentlichen Internet oder in nicht vertrauenswürdigen Netzen ist nicht vorgesehen.

Die zentrale Deployment-Konfiguration liegt in `config/deployment.json`; die Vorlage ist `config/deployment.example.json`. Im portablen Paket wird eine Standardkonfiguration mitgeliefert. Alternativ kann über `LOGSANITIZER_CONFIG` eine externe Konfigurationsdatei angegeben werden. Relative Pfade werden grundsätzlich relativ zum Speicherort der Konfigurationsdatei interpretiert.

## Standalone-Laptop

- Profil: `standalone`
- Bind-Adresse: `127.0.0.1` (nur lokaler Zugriff)
- Anmeldung: lokale Benutzerkonten
- LDAP und SMTP: nicht erforderlich
- Internetzugriff: nicht erforderlich

Das Programm wird unter Windows über `LogSanitizer.exe`, unter Linux über `./LogSanitizer` gestartet. Die Oberfläche wird lokal bereitgestellt und ist standardmäßig unter `http://127.0.0.1:8000` erreichbar.

Der erste Administrator wird einmalig über `LogSanitizer.exe --create-admin` beziehungsweise `./LogSanitizer --create-admin` angelegt. Benutzer und Rollen werden anschließend in der Anwendung verwaltet.

## Isoliertes Air-Gap-Netz

Für den Netzwerkbetrieb wird eine konkrete, für die vorgesehenen Clients erreichbare Schnittstellenadresse in `server.bind_host` konfiguriert. Der Netzwerkbetrieb bleibt auf das definierte isolierte Netz beschränkt; Firewall-Regeln sollen den Zugriff auf die vorgesehenen Clients begrenzen.

Das Netzwerkprofil unterstützt wahlweise lokale Benutzerkonten oder LDAP/Active Directory. Bei `auth.provider=local` und deaktiviertem LDAP werden lokale Konten verwendet; der erste Administrator kann wie im Standalone-Profil über `--create-admin` angelegt werden. Bei `auth.provider=ldap` muss `ldap.enabled=true` gesetzt sein; es gibt dann keinen lokalen Passwort-Fallback. LDAP wird mit LDAPS oder StartTLS betrieben. Zu konfigurieren sind Host/Port, Bind-DN, User-Search-Base, Benutzerfilter, Gruppenattribut und explizite Gruppenzuordnung zu den Rollen admin, rule_owner, operator, reviewer und approver. Das Dienstkonto-Geheimnis wird ausschließlich über die lokale Prozessumgebung bereitgestellt. Optional kann eine CA-Datei angegeben werden.

SMTP kann für Benachrichtigungen über ausstehende Reviews und Rückgaben aktiviert werden. Host, Port, Sicherheitsmodus (STARTTLS oder SSL), Absender und Empfängerlisten werden über die Deployment-Konfiguration festgelegt. Zugangsdaten werden ausschließlich über lokale Umgebungsvariablen bereitgestellt und niemals in die JSON-Datei oder das portable Paket geschrieben. SMTP-Ausfälle dürfen die Verarbeitung nicht blockieren.

Vor dem Start im Netzwerkprofil müssen echte LDAP-/SMTP-Endpunkte und Zertifikate aus der Zielumgebung eingetragen werden. Der Netzwerkzugriff bleibt auf das definierte Air-Gap-Netz begrenzt.

Das Netzwerkprofil verwendet HTTPS und benötigt dafür ein Zertifikat sowie einen privaten Schlüssel. Für LDAP-Verbindungen sind LDAPS oder StartTLS zu verwenden. Die Zertifikate und LDAP-Gruppen müssen aus der konkreten Air-Gap-Umgebung stammen.

## Daten, Mapping und Backups

Projekte, importierte Dateimetadaten, Review-Informationen und Mapping-Zuordnungen werden lokal in SQLite gespeichert. Die Mapping-Zuordnungen sind projektbezogen: derselbe Originalwert erhält innerhalb eines Projekts über mehrere Dateien hinweg denselben Ersatzwert.

Mapping-Zuordnungen werden direkt in der lokalen SQLite-Datenbank gespeichert. Eine separate Schlüsseldatei und eine Migration verschlüsselter Altbestände sind nicht Bestandteil der finalen Produktversion. Da vor dem finalen Einsatz keine echten Logs verarbeitet werden, beginnt die Produktivnutzung mit einer frisch angelegten Mapping-Datenbank. Eine vorhandene Mapping-Datenbank aus Entwicklungs- oder Testständen wird nicht übernommen.

Vor regulären Updates ist eine Sicherung des gesamten Datenverzeichnisses empfehlenswert. Ein Wiederherstellungstest stellt sicher, dass Projekte, Mapping-Zuordnungen und Review-Historie verfügbar bleiben.

## Ausgabe und Dateiverarbeitung

Quelldateien bleiben unverändert. Die Verarbeitung großer Dateien erfolgt streamend; vollständiges Einlesen einer Logdatei in den Arbeitsspeicher ist nicht vorgesehen. Die Ausgabe wird an einen vom Anwender gewählten Zielort geschrieben.

Der Anwender kann einen absoluten Ausgabepfad frei wählen. Der Zielordner muss bereits existieren; vorhandene Zieldateien werden nicht überschrieben. Eine Workspace-Allowlist oder ein zentral konfigurierter Ausgabeordner ist nicht erforderlich.

## Rollen und Review

Die Benutzer- und Rollenverwaltung bleibt Bestandteil des Produkts. Unterstützt werden die administrativen und fachlichen Aufgaben für Administration, Regelverantwortung, Verarbeitung sowie Review/Freigabe. Rollen können bei geringer Personalstärke einer Person zugeordnet und später auf mehrere Personen verteilt werden.

Ist ein Reviewer/Freigeber zugewiesen, bleibt die bewusste Prüfung und Freigabe Bestandteil des Ablaufs. Ohne zugewiesene Review-Rolle kann der Lauf automatisch freigegeben werden. Rückgabe, Abbruch, Kommentare und nachvollziehbare Statushistorie bleiben erhalten.

## Portable Builds

Die PyInstaller-Spezifikation erstellt ein portables Paket mit lokalem Frontend, Offline-Hilfe, Dokumentation und Beispielkonfiguration. Windows- und Linux-Pakete werden jeweils auf dem entsprechenden Betriebssystem gebaut. Die CI führt Frontend-Tests, Backend-Tests, Paket-Builds und Standalone-Smoke-Tests aus. Ein erfolgreicher Standalone-Smoke-Test beweist nicht die LDAP-/SMTP-Erreichbarkeit. Vor Freigabe sind mindestens erfolgreiche LDAP-Anmeldungen für die relevanten Rollen, ein abgewiesener Benutzer ohne passende Gruppe, Zertifikatsprüfung sowie SMTP-Zustellung für Review und Rückgabe im echten Air-Gap-Netz zu protokollieren.


## Backend-Konfiguration im Detail: LDAP/AD, TLS und SMTP

Dieser Abschnitt ist als ausführliche Offline-Betriebshilfe gedacht. Er beschreibt die vorhandenen Konfigurationsfelder und den tatsächlichen Anmeldeablauf. Die Datei `config/deployment.example.json` enthält syntaktisch gültige Beispielwerte mit der reservierten Domain `example.invalid`; diese Werte müssen vor dem Einsatz durch die Daten Ihrer Umgebung ersetzt werden.

### Wo die Konfiguration liegt

- Standarddatei: `config/deployment.json` im Konfigurationsverzeichnis des portablen Pakets bzw. der Anwendung.
- Vorlage: `config/deployment.example.json`.
- Alternative: `LOGSANITIZER_CONFIG` kann auf eine externe JSON-Datei zeigen.
- Relative Pfade für `data_dir`, TLS-Dateien und LDAP-CA-Datei werden relativ zum Verzeichnis der ausgewählten JSON-Datei aufgelöst.
- Konfigurationsdateien enthalten keine Passwörter oder sonstigen Geheimnisse. Der Loader weist JSON-Schlüssel zurück, die wie Passwort-, Secret- oder Token-Felder heißen.

Die wichtigsten Bereiche sind:

| Bereich | Aufgabe |
|---|---|
| `profile` | `standalone` oder `network` |
| `data_dir` | Speicherort der lokalen Datenbanken und Arbeitsdaten |
| `server` | Bind-Adresse, Port und HTTPS-Zertifikat des Webservers |
| `auth` | Anmeldeanbieter: `local` oder `ldap` |
| `ldap` | Verzeichnisserver, Suchkonto, Benutzersuche, TLS und Rollengruppen |
| `smtp` | optionale E-Mail-Benachrichtigungen |

### LDAP-Benutzerpasswort und technisches Suchkonto – zwei verschiedene Dinge

**Das persönliche LDAP-/AD-Benutzerpasswort wird bereits über das normale Passwortfeld der LogSanitizer-Anmeldeseite angenommen.** Bei `auth.provider=ldap` sendet die Oberfläche Benutzername und eingegebenes Passwort an den Backend-Anmeldeendpunkt. Das Backend verwendet dieses Passwort anschließend für einen LDAP-Bind mit dem gefundenen Benutzer-DN. Ein persönliches Client-Zertifikat des Anwenders ist dafür nicht erforderlich.

Daneben verwendet die derzeitige LDAP-Suche ein technisches Suchkonto:

- `ldap.bind_dn`: DN dieses technischen Dienst-/Lesekontos.
- `LOGSANITIZER_LDAP_BIND_PASSWORD`: Passwort genau dieses technischen Kontos.
- Das technische Konto sucht den Benutzer und liest dessen Gruppenattribute.
- Erst danach wird mit dem gefundenen persönlichen Benutzer-DN und dem Passwort aus dem LogSanitizer-Anmeldeformular ein zweiter Bind ausgeführt.

Das sind bewusst zwei getrennte Zugangsdaten. Das Dienstkonto-Passwort wird nicht als Passwort des angemeldeten Anwenders verwendet. Wenn die Anmeldeseite verwendet wird, ist das dort eingegebene Passwort das persönliche LDAP-/AD-Passwort des jeweiligen Mitarbeiters.

### LDAP-Verbindung und Zertifikate

Es gibt zwei zulässige Transportvarianten:

| Einstellung | LDAPS | LDAP mit StartTLS |
|---|---:|---:|
| `ldap.port` (üblich) | `636` | `389` |
| `ldap.use_ssl` | `true` | `false` |
| `ldap.start_tls` | `false` | `true` |

LDAPS verschlüsselt die Verbindung ab dem Verbindungsaufbau. Bei StartTLS wird zunächst die LDAP-Verbindung aufgebaut und anschließend TLS ausgehandelt. Der Bind mit Dienstkonto- oder Benutzerpasswort erfolgt erst nach erfolgreichem TLS-Aufbau. Unverschlüsseltes LDAP wird abgewiesen; LDAPS und StartTLS dürfen nicht gleichzeitig aktiviert sein.

Die Zertifikatsfelder haben unterschiedliche Aufgaben:

- `ldap.ca_certs_file`: optionaler Pfad zu einer CA-Zertifikatsdatei, mit der das Backend das **LDAP-Serverzertifikat** prüft. Das ist kein persönliches Benutzerzertifikat.
- `server.tls_certfile`: HTTPS-Zertifikat, mit dem sich der LogSanitizer-Webserver gegenüber Browsern ausweist.
- `server.tls_keyfile`: privater Schlüssel zum HTTPS-Serverzertifikat.

Der LDAP-Servername in `ldap.host` muss zum Zertifikat passen. Die Zertifikatsprüfung ist aktiv; ungültige oder nicht vertrauenswürdige LDAP-Serverzertifikate dürfen nicht durch Abschalten der Prüfung umgangen werden. Clients müssen außerdem dem HTTPS-Zertifikat des LogSanitizer-Servers vertrauen.

### LDAP-Felder

| Feld | Bedeutung / Beispiel |
|---|---|
| `enabled` | Muss bei LDAP-Anmeldung `true` sein. |
| `host` | DNS-Name des LDAP-/AD-Servers, z. B. `dc01.intern.example`. |
| `port` | LDAP-TLS-Port, typischerweise 636 oder 389 mit StartTLS. |
| `use_ssl` | `true` für LDAPS, sonst `false`. |
| `start_tls` | `true` für StartTLS, sonst `false`. |
| `ca_certs_file` | Optionaler CA-Dateipfad für die Prüfung des LDAP-Serverzertifikats. |
| `bind_dn` | Vollständiger DN des technischen Suchkontos. |
| `user_search_base` | Teilbaum, in dem Benutzer gesucht werden, z. B. `OU=Users,DC=intern,DC=example`. |
| `user_filter` | LDAP-Filter mit dem Platzhalter `{username}`. |
| `username_attribute` | Benutzerattribut für den LogSanitizer-Anmeldenamen; AD üblicherweise `sAMAccountName`. |
| `group_attribute` | Gruppenattribut; AD üblicherweise `memberOf`. |
| `role_groups` | Zuordnung der vollständigen Gruppen-DNs zu LogSanitizer-Rollen. |

Beispiele für Benutzerfilter:

- Active Directory mit Kurzname: `(sAMAccountName={username})`
- Active Directory mit UPN: `(userPrincipalName={username})`
- OpenLDAP mit UID: `(uid={username})`

Der Platzhalter `{username}` muss im Filter enthalten sein. Der eingegebene Benutzername wird vor dem Einsetzen in den Filter LDAP-gerecht maskiert. Die Suche muss genau einen Benutzer finden; kein oder mehrere Treffer führen zur Ablehnung.

### Gruppen und LogSanitizer-Rollen

Unter `role_groups` werden vollständige Gruppen-DNs hinterlegt. Unterstützte Schlüssel:

- `admin`: vollständige Administration und Benutzerverwaltung.
- `rule_owner`: Regeln und Quellprofile verwalten.
- `operator`: Projekte und Bereinigungsläufe bearbeiten.
- `reviewer`: Ergebnisse prüfen und zurückgeben.
- `approver`: Ergebnisse freigeben bzw. stoppen.

Die LDAP-Integration wertet aktuell direkte Mitgliedschaften des konfigurierten Gruppenattributs aus. Eine automatische rekursive Auflösung verschachtelter Active-Directory-Gruppen ist nicht implementiert. Ein Benutzer ohne mindestens eine passende konfigurierte Gruppe erhält keine Sitzung. Mehrere passende Gruppen ergeben mehrere Rollen.

LDAP-Identitäten werden lokal als externe Benutzerreferenzen geführt. Ein LDAP-Benutzer darf kein vorhandenes lokales Konto gleichen Namens übernehmen. Ein in LogSanitizer lokal deaktiviertes externes Konto bleibt gesperrt. Die Rollenzuordnung wird bei erfolgreicher Anmeldung anhand der aktuellen Gruppenmitgliedschaften aktualisiert. Bei LDAP-Fehlern gibt es keinen Rückfall auf lokale Passwörter.

### Geheimnisse als Prozessumgebungsvariablen bereitstellen

Folgende Variablen werden unterstützt:

| Variable | Zweck |
|---|---|
| `LOGSANITIZER_LDAP_BIND_PASSWORD` | Passwort des technischen LDAP-Suchkontos; im LDAP-Netzwerkprofil erforderlich. |
| `LOGSANITIZER_SMTP_USERNAME` | SMTP-Anmeldename; optional. |
| `LOGSANITIZER_SMTP_PASSWORD` | SMTP-Passwort; optional, muss zusammen mit dem Benutzernamen gesetzt sein. |
| `LOGSANITIZER_CONFIG` | Optionaler vollständiger Pfad zur Deployment-JSON-Datei. |
| `LOGSANITIZER_DATA_DIR` | Optionaler Datenverzeichnis-Override. |

Die Variablen müssen in der Umgebung des Prozesses vorhanden sein, der LogSanitizer startet. Bei einem Windows-Dienst oder Linux-Systemdienst sind sie im Dienstmanager bzw. in einer lokal geschützten Environment-Datei einzurichten. Für manuelle Tests können sie vor dem Start in der jeweiligen Shell gesetzt werden. Keine Passwörter in JSON-Dateien, Git, Startargumenten, Screenshots oder Diagnoseausgaben hinterlegen. Nach Änderung einer Prozessumgebungsvariablen muss der Backend-Prozess neu gestartet werden.

### SMTP-Benachrichtigungen

SMTP ist optional und wird nur im Netzwerkprofil verwendet. Die JSON-Felder:

- `enabled`: Versand aktivieren.
- `host` und `port`: SMTP-Server und Port.
- `security`: `starttls` oder `ssl`; Klartext-SMTP ist nicht zulässig.
- `from`: Absenderadresse.
- `reviewer_emails`: Empfänger für neue ausstehende Prüfungen.
- `operator_emails`: Empfänger für zurückgegebene Läufe.

Falls der SMTP-Server Anmeldung verlangt, müssen `LOGSANITIZER_SMTP_USERNAME` und `LOGSANITIZER_SMTP_PASSWORD` gemeinsam gesetzt sein. SMTP-Fehler dürfen Bereinigung und Freigabe nicht blockieren. E-Mails enthalten keine Log-Inhalte, Passwörter, Mappings oder absoluten Dateipfade.

### Beispiel: LDAP-/AD-Netzwerkprofil

Das folgende Beispiel zeigt die Struktur; Hostnamen, DNs, Gruppen, Zertifikatspfade und E-Mail-Adressen sind durch echte Werte der Zielumgebung zu ersetzen:

```json
{
  "profile": "network",
  "data_dir": "./data",
  "server": {
    "bind_host": "10.20.30.40",
    "port": 8443,
    "tls_certfile": "./certs/logsanitizer-server.crt",
    "tls_keyfile": "./certs/logsanitizer-server.key"
  },
  "auth": { "provider": "ldap" },
  "ldap": {
    "enabled": true,
    "host": "dc01.intern.example",
    "port": 636,
    "use_ssl": true,
    "start_tls": false,
    "ca_certs_file": "./certs/directory-ca.pem",
    "bind_dn": "CN=logsanitizer-reader,OU=Service Accounts,DC=intern,DC=example",
    "user_search_base": "OU=Users,DC=intern,DC=example",
    "user_filter": "(sAMAccountName={username})",
    "username_attribute": "sAMAccountName",
    "group_attribute": "memberOf",
    "role_groups": {
      "admin": "CN=LogSanitizer-Admins,OU=Groups,DC=intern,DC=example",
      "rule_owner": "CN=LogSanitizer-Rule-Owners,OU=Groups,DC=intern,DC=example",
      "operator": "CN=LogSanitizer-Operators,OU=Groups,DC=intern,DC=example",
      "reviewer": "CN=LogSanitizer-Reviewers,OU=Groups,DC=intern,DC=example",
      "approver": "CN=LogSanitizer-Approvers,OU=Groups,DC=intern,DC=example"
    }
  },
  "smtp": {
    "enabled": true,
    "host": "mail.intern.example",
    "port": 587,
    "security": "starttls",
    "from": "logsanitizer@intern.example",
    "reviewer_emails": "reviewers@intern.example",
    "operator_emails": "operators@intern.example"
  }
}
```

Zusätzlich muss `LOGSANITIZER_LDAP_BIND_PASSWORD` mit dem Passwort des Dienstkontos gesetzt sein. Jeder Anwender meldet sich anschließend auf der LogSanitizer-Anmeldeseite mit seinem persönlichen LDAP-Benutzernamen und seinem persönlichen LDAP-Passwort an.

### Inbetriebnahme und Fehlersuche

1. Zuerst DNS-Auflösung und Netzwerkverbindung vom LogSanitizer-Rechner zum LDAP-Server prüfen.
2. Zertifikatskette und Gültigkeitszeitraum des LDAP-Serverzertifikats prüfen; der verwendete Hostname muss im Zertifikat enthalten sein.
3. Bind-DN und Dienstkonto-Passwort kontrollieren. Das Dienstkonto muss die Suche in `user_search_base` und das Lesen der Gruppenattribute ausführen dürfen.
4. Den Benutzerfilter mit einem bekannten Benutzernamen prüfen und sicherstellen, dass genau ein Eintrag gefunden wird.
5. Mit dem persönlichen LDAP-Passwort des Benutzers anmelden. Ein falsches Benutzerpasswort muss mit HTTP 401 abgewiesen werden; es darf keine lokale Anmeldung versuchen.
6. Prüfen, ob das Gruppenattribut die erwarteten direkten Gruppen-DNs enthält und diese exakt den Werten in `role_groups` entsprechen (Groß-/Kleinschreibung wird bei der Zuordnung ignoriert).
7. Für jede Rolle mindestens einen Testbenutzer verwenden; zusätzlich einen Benutzer ohne zugeordnete Gruppe testen.
8. SMTP getrennt testen: Zustellung für neue Review-Aufgabe und Rückgabe an die jeweils konfigurierten Empfänger prüfen.

Die CI testet LDAP-Anmeldeabläufe mit simulierten LDAP-Ergebnissen und prüft den Netzwerkprofil-Paketstart. Sie ersetzt keinen Test gegen den echten Active Directory-/LDAP- und SMTP-Server im Air-Gap-Netz.

## Automatisierte Netzwerkprofil-Prüfung

Die CI startet das portable Paket zusätzlich einmal mit dem Netzwerkprofil, einem zur Laufzeit erzeugten lokalen TLS-Zertifikat sowie synthetischer LDAP- und SMTP-Konfiguration. Damit werden PyInstaller-Start, Konfigurationsprüfung und HTTPS-Erreichbarkeit des Netzwerkprofils auf Windows und Linux abgedeckt.

Dieser Smoke-Test verbindet sich absichtlich nicht mit einem echten LDAP- oder SMTP-Server. Vor der Inbetriebnahme im Air-Gap-Netz sind deshalb echte LDAP-Anmeldung, Gruppenzuordnung, Zertifikatskette und SMTP-Zustellung gemäß der obigen Abnahmeliste zu testen.
