# Roadmap

> **Baseline v2.8 (2026-10-29):** Performance and usability take priority for Standalone-Laptop and defined Air-Gap operation. High-security hardening items are no longer release gates; user accounts, roles, review/approval and audit remain required. See [REQUIREMENTS.md](REQUIREMENTS.md).

## Meilenstein 0 — Grundgerüst
- [x] Anforderungen v2.7 dokumentieren.
- [x] FastAPI-Health-Endpunkt und Test.
- [x] React/TypeScript-Oberfläche mit lokal eingebundener Hilfe.
- [x] Backend-/Frontend-Tests und Frontend-Build lokal erfolgreich ausgeführt.
- [ ] Installations- und Testbefehle unter Windows und Linux verifizieren.

## Meilenstein 1 — Sicherer lokaler Kern
- [x] Projektverwaltung: Projekte anlegen, auflisten und öffnen.
- [x] SQLite-Metadatenschema mit Schema-Versionierung.
- [x] Einzeldatei registrieren: nur Metadaten speichern, Original unverändert lassen.
- [x] Backend-Ordnerregistrierung mit Fehlerliste, Duplikatbehandlung und Begrenzung auf 5.000 Dateien.
- [x] UI für Einzeldatei-/Ordnerregistrierung mit expliziter Aktion, rekursiver Option und Fehlerliste (absolute Pfade; nativer Dateiauswahldialog bleibt offen).
- [x] Konservativer Dateiendungs-Hinweis (`format_hint`) inklusive `unknown`; keine Inhaltsprüfung bei Registrierung.
- [x] Explizite heuristische Formaterkennung anhand einer lokalen Stichprobe von höchstens 64 KiB; Ergebnis lokal speichern.
- [x] Manuelle Format-Auswahl pro Datei speichern und wieder entfernen.
- [x] Explizite vollständige Formatvalidierung für Text, JSON, JSON Lines, CSV und XML über Backend-Endpunkt und UI; unbekannte Formate werden nicht als gültig bestätigt. Die Validierung prüft Syntax, nicht die Erkennung sensibler Daten.
- [x] Versionierte JSON-Regelkonfiguration v1 mit Schema-, Regex-, Profilreferenz- und Konfliktprüfung; lokale atomare Speicherung über API. Die Regeln werden auf unterstützte Text- und JSONL-Dateien angewendet.
- [x] Erste zeilenweise Streaming-Ausführung für UTF-8-Text und JSON Lines mit Regelpriorität, optionalem Quellprofil, separater Ausgabe und Fehlerbereinigung; maximale Eingabezeile 1 MiB. Vollständige JSON-Dokumente und weitere Formate bleiben offen.
- [ ] Mapping-Speicherung auf einfache lokale SQLite-Struktur zurückführen; AES-Verschlüsselung, separate Schlüsseldatei, HMAC-Sonderlogik und aufwendige Schlüsselmigration gemäß Anforderungen v2.8 entfernen. Projektweite konsistente Platzhalter bleiben erhalten. Bestehende Daten vor einer Migration berücksichtigen.
- [x] Fortschrittsanzeige und kooperativer Abbruch für Hintergrundläufe; Verarbeitung meldet Phase, Bytes und Zeilen.
- [x] Ausgabe wird in einer temporären Datei im Zielordner erzeugt, validiert und erst danach ohne Überschreiben veröffentlicht; temporäre Datei wird bei regulärem Erfolg, Fehler oder Abbruch entfernt.
- [ ] Ausgabe-/Arbeitsbereich vereinfachen: frei wählbare Ausgabepfade statt verpflichtender Workspace-Allowlist; unnötige Pfad-/Symlink-Sonderlogik gemäß Anforderungen v2.8 entfernen, Quelldateien weiterhin unverändert lassen.
- [x] LS-SEC-003 race-resistente Veröffentlichung ist nach Anforderungen v2.8 kein Produktziel mehr. Die aufwendige Race-Härtung wird nicht umgesetzt; einfache, zuverlässige Dateiausgabe mit Fehlerbereinigung bleibt erforderlich.
- [x] Dauerhafte Lauf-/Prüfhistorie mit Ergebniskennzahlen, Status, Kommentaren, Ausnahmebegründungen und Audit-Ereignissen in einer separaten lokalen SQLite-Datenbank.
- [x] Dauerhafte Hintergrundjob-Status-/Fortschrittsdaten in SQLite; beim Start verwaiste Läufe als `interrupted` markieren und zugehörige verwaiste Staging-Dateien sicher bereinigen.
- [x] Pflichtvalidierung nach der Bereinigung: Ausgabe vollständig zeilenweise erneut lesen, UTF-8/JSONL-Syntax prüfen und alle aktiven konfigurierten Muster auf Resttreffer scannen; bei Fehlern Ausgabe löschen und Lauf ablehnen. Gilt nur für unterstützte Text-/JSONL-Ausgabe und ist kein Beweis vollständiger Geheimniserkennung.

## Meilenstein 2 — Prüfung und kontrollierte Freigabe
- [x] Lokale Anmeldung, serverseitige Rollenprüfungen und Login-Oberfläche; Authentifizierungs- und Regressionstests in CI erfolgreich.
- [x] Prüfer-Warteschlange und sichere wörtliche Stichprobensuche ausschließlich in bereinigten Ausgaben; eigene gespeicherte Suchmuster.
- [x] Freigabe, Rückgabe, Stopp und Kommentare; Laufhistorie und unveränderliche Audit-Ereignisse.
- [x] Eng begrenzte, ausdrücklich begründete Ausnahmen; fehlgeschlagene Pflichtvalidierungen bleiben nicht freigabefähig.
- [ ] Rollen- und Berechtigungstests für Administrator, Rule Owner, Processor und Reviewer/Releaser; Rollen und Freigabeworkflow bleiben verbindlich, ohne umfassendes Hochsicherheits-Audit.

## Meilenstein 3 — Deployment
- [x] Optionale SMTP-Benachrichtigungen für ausstehende Prüffreigaben und zurückgegebene Läufe; Konfiguration über lokale Umgebungsvariablen und automatisierte Tests.
- [x] Optionale LDAP/AD-Anmeldung im Netzwerkprofil: LDAPS oder StartTLS, explizite LDAP-Gruppen-Zuordnung zu Rollen, keine lokale Passwort-Fallback-Anmeldung; Konfiguration aus JSON plus Dienstkonto-Geheimnis aus der Umgebung. Live-Verbindung zu einer echten LDAP/AD-Instanz bleibt ein Integrationstest vor Freigabe.
- [x] Explizite Deployment-Profile: Standalone nur Loopback/lokale Konten/SMTP aus; Netzwerkprofil benötigt LDAP, geschützte Bind-Adresse und TLS-Zertifikat/Schlüssel und startet HTTPS. Netzwerk- und TLS-Betrieb muss vor Freigabe gegen die Zielumgebung geprüft werden.
- [x] Portable Windows-/Linux-CI-Paketierung: PyInstaller-One-Folder-Build und Standalone-Health-Smoke-Test auf `windows-latest` und `ubuntu-latest` erfolgreich (GitHub Actions Lauf 40936541846, 2026-10-29). Dies bestätigt den CI-Build, ersetzt aber noch keine Installationstests auf den tatsächlich unterstützten Zielversionen.
- [ ] Offline-Handbuch und portable Pakete auf den tatsächlichen Zielversionen von Windows/Linux prüfen; Netzwerkprofil zusätzlich separat paketiert und gegen die Zielumgebung testen.
- [ ] Performanceprüfung mit Testdateien >= 5 GB (Laufzeit, RAM/CPU, UI-Reaktionsfähigkeit); Bedienbarkeit und typische Arbeitsabläufe testen.

## Aktueller Validierungsstand (2026-10-29)\n- [x] CI-Lauf 40955808621 (Commit 9045e35): Backend Linux, Backend Windows, Frontend sowie portable Builds/Smoke-Tests Linux und Windows erfolgreich.\n- [x] Issue #3 zur verpflichtenden Workspace-Allowlist gemäß v2.8 als nicht mehr geplant geschlossen; dies ist keine Aussage über Race-Resistenz der bisherigen Implementierung.\n\n## Definition of done
Eine Funktion benötigt Tests, verständliche Offline-Hilfe, sicheres Fehlerverhalten und Dokumentation. Sicherheitsfunktionen müssen auch abgewiesene/unzulässige Pfade testen.

## Umstellung auf Anforderungen v2.8
- [ ] Bestehende Mapping-Verschlüsselung und Schlüsseldatei durch einfache lokale Mapping-Speicherung ersetzen; Migration/Kompatibilität klären. Deployment-Dokumentation weist auf den Übergangszustand hin.
- [ ] Konfigurierbaren Ausgabeort ohne verpflichtende Workspace-Allowlist im Backend umsetzen (Dokumentation angepasst).
- [x] Deployment-Dokumentation auf v2.8 ausgerichtet: Standalone-Laptop und definiertes Air-Gap-Netz; LDAP/SMTP als optionale Netzwerkfunktionen. Die Laufzeitumstellung ist davon getrennt und noch offen.
- [ ] Rollen, Prüferworkflow, Freigabe/Rückgabe und Audit regressionssicher erhalten.
- [ ] Performance- und Usability-Schwerpunkt: 5-GB-Tests, Speicherprofile, UI-Reaktionszeiten und kurze Bedienwege.
