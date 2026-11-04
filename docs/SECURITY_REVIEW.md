# Sicherheits- und Betriebsbewertung — LogSanitizer v2.8

**Stand:** 2026-11-04  
**Geltungsbereich:** Eigenständiger Windows-/Linux-Laptop oder ein ausdrücklich definiertes, internetgetrenntes Air-Gap-Netz. Kein Betrieb im öffentlichen Internet oder in nicht vertrauenswürdigen Netzen.  
**Einordnung:** Technische Bestandsaufnahme des Entwicklungsstands, keine Penetrationsprüfung, Zertifizierung oder unabhängige Sicherheitsfreigabe.

## Verbindliche Produktgrenzen

Mit Anforderungsstand v2.8 wurden frühere High-Security-Sonderanforderungen ausdrücklich zurückgenommen. Die folgenden Entscheidungen sind daher kein versehentlich offener Implementierungsstand:

- Mapping-Zuordnungen werden projektbezogen in der lokalen SQLite-Datenbank gespeichert; eine zusätzliche Verschlüsselung mit separater Schlüsseldatei ist nicht Bestandteil der Produktanforderung.
- Es gibt keine verpflichtende Workspace-Allowlist für Ausgabeziele. Der Bearbeiter wählt den absoluten Ausgabepfad; vorhandene Zieldateien werden nicht überschrieben.
- Eine besondere Absicherung gegen einen absichtlich parallel manipulierenden lokalen Prozess und plattformspezifische ACL-Sonderlogik sind nicht Teil des vereinbarten Umfangs.
- Eine Migration von Entwicklungs-Mappings ist nicht vorgesehen. Der Produktivbetrieb beginnt mit einer frischen Datenbank.

Diese Vereinfachungen gelten nur innerhalb des festgelegten Einsatzmodells. Sie sind keine Empfehlung, die Anwendung öffentlich oder in einem nicht vertrauenswürdigen Netzwerk bereitzustellen.

## Umgesetzte technische Kontrollen

### Anmeldung und Sitzungen

- Lokale Passwörter werden mit scrypt und individuellem Salt gespeichert.
- Sitzungen verwenden zufällige Tokens; in der Datenbank liegt nur deren SHA-256-Hash.
- Sitzungsdauer ist begrenzt; deaktivierte Benutzer verlieren ihre Sitzungen.
- Fehlversuche werden je normalisiertem Benutzernamen und Client-Adresse begrenzt: fünf Fehlversuche innerhalb von fünf Minuten führen zu einer fünfminütigen Sperre.
- Zustandsändernde API-Aufrufe erfordern ein CSRF-Token.
- Die Login-Oberfläche unterstützt lokale Konten oder — im entsprechend konfigurierten Netzwerkprofil — LDAP/AD. Bei LDAP gibt es keinen lokalen Passwort-Fallback.

### Rollen und Review

- Rollen: Administrator, Regelverantwortlicher, Bearbeiter, Prüfer und Freigeber.
- Die Middleware prüft Anmeldung, CSRF und zentrale Rollenbereiche; zusätzliche Endpunktprüfungen sichern insbesondere Eigentümerschaft und Dateivergleich.
- Die Benutzerverwaltung verhindert das Entfernen des letzten aktiven Administrators.
- Zurückgewiesene Läufe, Kommentare, Freigaben und Prüfentscheidungen werden im Review-/Audit-Ablauf nachvollziehbar geführt.

**Verbleibende Einschränkung:** Es liegt keine vollständige tabellarische Negativprüfung jeder API-Route gegen jede Rolle einschließlich aller kodierten Pfadvarianten vor. Vor einem Einsatz mit besonders hohen Schutzanforderungen ist diese Matrix zu ergänzen und unabhängig zu prüfen.

### Regelverarbeitung und große Dateien

- Regelbasierte Regex-Operationen verwenden die Timeout-fähige `regex`-Bibliothek mit 100 ms je Substitutions-/Suchoperation. Ein Timeout lässt den Lauf fehlschlagen; unvollständige Ausgabe wird entfernt.
- Dies ist kein globales Job-, CPU- oder Parallelitätsbudget.
- Die Erkennung und Restprüfung können nur die konfigurierten Regeln berücksichtigen. Sie stellen keine vollständige automatische Erkennung sämtlicher personenbezogener oder vertraulicher Daten dar.
- Streaming und synthetische große-Datei-Prüfungen sind implementiert; Zielhardwaremessungen bleiben separat durchzuführen.

### Netzwerkprofil, LDAP und SMTP

- Standalone ist auf Loopback beschränkt.
- Das Netzwerkprofil verlangt eine konkrete Bind-Adresse und HTTPS-Zertifikat/Schlüsseldatei; Sitzungs-Cookies werden mit Secure gesetzt.
- LDAP muss LDAPS oder StartTLS verwenden. Das Serverzertifikat wird geprüft; Benutzername und Gruppenmitgliedschaften werden über das konfigurierte Suchkonto ermittelt, danach wird das persönliche LDAP-Passwort mit dem gefundenen Benutzer-DN geprüft.
- SMTP muss STARTTLS oder SSL verwenden. Zustellfehler blockieren die Bereinigung nicht.

**Verbleibende Einschränkung:** Die Konfigurationsprüfung ersetzt keine Prüfung der echten Zertifikatskette, Firewall-/Netzwerkgrenzen oder Verzeichnisrechte. LDAP/AD-Anmeldung, Gruppenabbildung, Zertifikate und SMTP-Zustellung müssen in der konkreten Air-Gap-Umgebung abgenommen werden. SMTP besitzt keine persistente Wiederholungswarteschlange.

### Dateiziele und lokale Daten

- Quelldateien bleiben unverändert.
- Ausgabeziele werden vom Bearbeiter gewählt; vorhandene Zieldateien werden nicht überschrieben.
- Mapping-Daten und Projektmetadaten liegen lokal in SQLite. Es gibt keine zusätzliche Verschlüsselung der Mapping-Datenbank.
- Wer Zugriff auf das lokale Datenverzeichnis erhält, kann je nach Betriebssystemrechten auch auf die dort gespeicherten Mapping-Zuordnungen zugreifen. Das lokale Benutzerkonto und der physische Zugriff auf das Gerät bleiben deshalb Teil des vereinbarten Schutzmodells.

## CI-Nachweis

Für Branch-Head `d257153f37213c2aa41ecbcfb02f59a3d9baac1c` wurde GitHub-Actions-Lauf [#41917675532](https://github.com/Ineedat/ChatGPT/actions/runs/41917675532) vollständig erfolgreich abgeschlossen:

- Linux-Backend: vollständige Pytest-Suite und Ruff erfolgreich.
- Windows-Backend: gezielte Projekt-/Mapping-Regressionen und Ruff erfolgreich.
- Frontend: Vitest-Tests und TypeScript-/Vite-Produktionsbuild erfolgreich.

Der reguläre CI-Lauf führt keinen vollständigen 5-GiB-Zielhardwaretest und keinen realen LDAP-/SMTP-Test durch. Der separate manuelle Meilenstein-Workflow für portable Windows-/Linux-Pakete und den 5-GiB-Benchmark ist davon unabhängig. CI-Erfolg ist kein Ersatz für die nachfolgende Systemabnahme.

## Vor dem produktiven Einsatz weiterhin erforderlich

1. Anwendung ausschließlich im vereinbarten Standalone-/Air-Gap-Einsatzmodell betreiben und Netzwerkzugriffe auf die vorgesehenen Clients begrenzen.
2. Auf realen Windows-/Linux-Zielsystemen portable Pakete, Dateirechte, UI-Verhalten und Ressourcenverbrauch prüfen.
3. Den manuellen Meilenstein-Workflow mit portablem Paket-Smoke-Test und synthetischem 5-GiB-Benchmark ausführen.
4. Im echten Air-Gap-Netz LDAP-/AD-Anmeldung für alle benötigten Rollen, Benutzer ohne passende Gruppe, Zertifikatsprüfung sowie SMTP-Benachrichtigungen für Review und Rückgabe testen.
5. Datenverzeichnis und Mapping-Datenbank in die lokale Backup-/Wiederherstellungsroutine aufnehmen und eine Wiederherstellung praktisch prüfen.

## Zusammenfassung

Die automatisierte Code-CI auf dem aktuellen Branch-Head ist grün. Die im Anforderungsstand v2.8 bewusst entfernten High-Security-Funktionen sind keine Merge-Blocker. Offen bleiben reale Zielsystem- und Air-Gap-Abnahmen sowie die ausdrücklich benannten Grenzen (keine Mapping-Verschlüsselung, keine vollständige automatische Datenerkennung, kein globales Ressourcenbudget und keine unabhängige Sicherheitszertifizierung).