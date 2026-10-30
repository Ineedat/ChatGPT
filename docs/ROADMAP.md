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
- [x] Streaming-Ausführung für UTF-8-Text, JSON Lines und vollständige JSON-Dokumente mit Regelpriorität, optionalem Quellprofil, separater Ausgabe und Fehlerbereinigung. Text/JSONL-Zeilen und einzelne JSON-Strings sind auf 1 MiB begrenzt; JSON-Schlüssel und -Werte werden regelbasiert verarbeitet. XML/CSV bleiben Validierungs-, keine Bereinigungsformate.
- [x] Neue Mapping-Speicherung auf einfache lokale SQLite-Struktur zurückgeführt; produktive Nutzung beginnt mit einer frischen Datenbank. Keine Migration von Entwicklungs-/Testbeständen.
- [x] Fortschrittsanzeige und kooperativer Abbruch für Hintergrundläufe; Verarbeitung meldet Phase, Bytes und Zeilen.
- [x] Ausgabe wird in einer temporären Datei im Zielordner erzeugt, validiert und erst danach ohne Überschreiben veröffentlicht; temporäre Datei wird bei regulärem Erfolg, Fehler oder Abbruch entfernt.
- [x] Frei wählbare absolute Ausgabepfade ohne Workspace-Allowlist; Zielordner muss existieren, bestehende Ziele werden nicht überschrieben und Quelldateien bleiben unverändert.
- [x] LS-SEC-003 race-resistente Veröffentlichung ist nach Anforderungen v2.8 kein Produktziel mehr. Die aufwendige Race-Härtung wird nicht umgesetzt; einfache, zuverlässige Dateiausgabe mit Fehlerbereinigung bleibt erforderlich.
- [x] Dauerhafte Lauf-/Prüfhistorie mit Ergebniskennzahlen, Status, Kommentaren, Ausnahmebegründungen und Audit-Ereignissen in einer separaten lokalen SQLite-Datenbank.
- [x] Dauerhafte Hintergrundjob-Status-/Fortschrittsdaten in SQLite; beim Start verwaiste Läufe als `interrupted` markieren und zugehörige verwaiste Staging-Dateien sicher bereinigen.
- [x] Pflichtvalidierung nach der Bereinigung: Ausgabe vollständig zeilenweise erneut lesen, UTF-8/JSONL-Syntax prüfen und alle aktiven konfigurierten Muster auf Resttreffer scannen; bei Fehlern Ausgabe löschen und Lauf ablehnen. Gilt nur für unterstützte Text-/JSONL-Ausgabe und ist kein Beweis vollständiger Geheimniserkennung.

## Meilenstein 2 — Prüfung und kontrollierte Freigabe
- [x] Lokale Anmeldung, serverseitige Rollenprüfungen und Login-Oberfläche; Authentifizierungs- und Regressionstests in CI erfolgreich.
- [x] Prüfer-Warteschlange und sichere wörtliche Stichprobensuche ausschließlich in bereinigten Ausgaben; eigene gespeicherte Suchmuster.
- [x] Freigabe, Rückgabe, Stopp und Kommentare; Laufhistorie und unveränderliche Audit-Ereignisse.
- [x] Eng begrenzte, ausdrücklich begründete Ausnahmen; fehlgeschlagene Pflichtvalidierungen bleiben nicht freigabefähig.
- [x] Rollen- und Berechtigungstests: Operator-/Reviewer-/Approver-/Admin-Trennung, kombinierte Rollen, Review-Entscheidungen, Such-/Kommentar-/Audit-Zugriff und Fail-closed-Verhalten bei unbekannter Prüferzuordnung; CI erfolgreich.

## Meilenstein 3 — Deployment
- [x] Optionale SMTP-Benachrichtigungen für ausstehende Prüffreigaben und zurückgegebene Läufe; Konfiguration über lokale Umgebungsvariablen und automatisierte Tests.
- [x] Optionale LDAP/AD-Anmeldung im Netzwerkprofil: LDAPS oder StartTLS, explizite LDAP-Gruppen-Zuordnung zu Rollen, keine lokale Passwort-Fallback-Anmeldung; Konfiguration aus JSON plus Dienstkonto-Geheimnis aus der Umgebung. Live-Verbindung zu einer echten LDAP/AD-Instanz bleibt ein Integrationstest vor Freigabe.
- [x] Explizite Deployment-Profile: Standalone nur Loopback/lokale Konten/SMTP aus; Netzwerkprofil benötigt eine geschützte Bind-Adresse und TLS-Zertifikat/Schlüssel und startet HTTPS; Authentifizierung ist wahlweise lokal oder über LDAP/AD möglich, SMTP bleibt optional. Netzwerk- und TLS-Betrieb muss vor Freigabe gegen die Zielumgebung geprüft werden.
- [x] Portable Windows-/Linux-CI-Paketierung: PyInstaller-One-Folder-Build und Standalone-Health-Smoke-Test auf `windows-latest` und `ubuntu-latest` erfolgreich (GitHub Actions Lauf 40936541846, 2026-10-29). Dies bestätigt den CI-Build, ersetzt aber noch keine Installationstests auf den tatsächlich unterstützten Zielversionen.
- [ ] Offline-Handbuch und portable Pakete auf den tatsächlichen Zielversionen von Windows/Linux prüfen; Netzwerkprofil zusätzlich separat paketiert und gegen die Zielumgebung testen.
- [x] Streaming-Speicherregression: 64-MiB-Testdatei mit begrenztem Python-Speicherverbrauch in CI; zusätzlicher optionaler 5-GiB-End-to-End-Test über `LOGSANITIZER_RUN_5GB_TEST=1`.
- [x] Reproduzierbares synthetisches Performance-Benchmark-Skript mit Laufzeit, CPU, Durchsatz, Python-Tracemalloc und Prozess-RSS ergänzt; kleiner Benchmark unter Windows/Linux und vollständiger 5-GiB-Lauf auf GitHub-Linux-Runner in CI vorgesehen.
- [ ] 5-GiB-Test auf dedizierter Zielhardware ausführen und Laufzeit, RAM/CPU sowie UI-Reaktionsfähigkeit dokumentieren; Bedienbarkeit und typische Arbeitsabläufe testen. Siehe PERFORMANCE.md.

## Aktueller Validierungsstand (2026-10-30)

- [x] Vollständige JSON-Dokumente sind jetzt als Bereinigungsformat freigegeben und werden mit einem Streaming-Parser verarbeitet; Ausgabe wird erneut strukturell und auf Resttreffer geprüft.
- [x] Offline-Hilfe wurde um konkrete Arbeitsabläufe, JSON-Verhalten, große Dateien und Deployment erweitert; F1 öffnet die Hilfe.
- [x] Portable-Paket-CI prüft Standalone und HTTPS-Netzwerkprofil unter Windows und Linux; lokaler Netzwerk-Login und LDAP-Konfigurationspfad sind durch Backend-Tests abgedeckt. Echte LDAP-/SMTP-Zielintegration bleibt ein manueller Abnahmeschritt, da keine Air-Gap-Verzeichnis- oder Mailserver verfügbar sind.
- [x] Vollständiger synthetischer 5-GiB-CI-Referenzlauf erfolgreich: 96,806 s, 52,89 MiB/s, maximaler Prozess-RSS 40.443.904 Byte; Messprotokoll in PERFORMANCE.md. Zielhardwaremessung bleibt offen.

- [x] CI-Lauf 41128457176 (Commit 19f7e53): alle fünf Jobs erfolgreich; vollständiger 5-GiB-Referenzlauf auf Linux erfolgreich. Push-CI-Lauf 41128449589 ebenfalls vollständig erfolgreich.
- [x] Backend-Windows-Job erfolgreich; dieser Job führt aktuell nur den gezielten Mapping-Test aus, nicht die vollständige Backend-Suite.
- [x] Rollenmatrix, Review-Entscheidungen, Operator-Berechtigungsgrenzen und Rückgabe-Benachrichtigung sind durch Tests abgedeckt.
- [x] Issue #3 zur verpflichtenden Workspace-Allowlist gemäß v2.8 als nicht mehr geplant geschlossen; dies ist keine Aussage über Race-Resistenz der bisherigen Implementierung.

## Definition of done
Eine Funktion benötigt Tests, verständliche Offline-Hilfe, sicheres Fehlerverhalten und Dokumentation. Sicherheitsfunktionen müssen auch abgewiesene/unzulässige Pfade testen.

## Umstellung auf Anforderungen v2.8
- [x] Mapping-Verschlüsselung durch einfache lokale Mapping-Speicherung ersetzt; keine Migration von Entwicklungs-/Testdatenbanken.
- [x] Backend-Ausgabeort ohne verpflichtende Workspace-Allowlist umgesetzt; die veraltete Deployment-Einstellung wurde entfernt.
- [x] Deployment-Dokumentation auf v2.8 ausgerichtet: Standalone-Laptop und definiertes Air-Gap-Netz; LDAP/SMTP als optionale Netzwerkfunktionen. Die Laufzeitumstellung ist davon getrennt und noch offen.
- [x] Rollen, Prüferworkflow, Freigabe/Rückgabe und Audit mit Regressionstests abgesichert; CI erfolgreich.
- [ ] Performance- und Usability-Schwerpunkt: 5-GiB-Lauf auf tatsächlicher Zielhardware, CPU-/RAM-/Laufzeitprofile, UI-Reaktionszeiten und kurze Bedienwege. CI-Referenzmessung liegt vor; die Zielhardware-Abnahme ist weiterhin offen.


## Priorisierte nächste Entwicklungsschritte

### Priorität 1 — Regelverwaltung und erste fachlich nutzbare Konfiguration
- [ ] Grafischer Regeleditor: Regeln anlegen, bearbeiten, kopieren, löschen und aktivieren/deaktivieren; globale und quellprofilspezifische Regeln; Kategorien, Suchart, Ersetzung, Mapping-Präfix und Priorität.
- [ ] Quellprofile in der Oberfläche anlegen, bearbeiten und löschen; verwendete Profile vor versehentlichem Löschen schützen.
- [ ] Regelkonfiguration vor dem Speichern serverseitig validieren und Konflikte verständlich anzeigen.
- [ ] Integrierte Musterprüfung/Vorschau mit synthetischen Beispielen und Anzeige der Treffer/Ersetzungen.
- [ ] Fachlich geprüfte Standard-Regelbibliothek für IP-Adressen, Hostnamen/Domains, Benutzer, E-Mail-Adressen, personenbezogene Daten, Passwörter/Tokens/API-Keys, Pfade und Infrastrukturinformationen.
- [ ] GUI-Import und -Export versionierter JSON-Regelkonfigurationen inklusive Vorschau und Validierung vor Übernahme.
- [ ] Vollständigen Projektablauf in der Oberfläche verbinden: Projekt, Dateien, Format, Quellprofil/Regeln, Bereinigung, Validierung und Freigabe.

### Priorität 2 — Abnahme und Freigabe
- [ ] End-to-End-Berechtigungstests für Regelverwaltung: Administrator/Rule Owner dürfen Regeln ändern; Processor darf Regeln anwenden, aber nicht bearbeiten.
- [ ] Review-/Freigabeablauf in der GUI vervollständigen und mit dem vollständigen Bereinigungsablauf verbinden.
- [ ] Zielsystem-Abnahme unter unterstützten Windows-/Linux-Versionen, inklusive 5-GiB-Datei, Abbruch/Wiederanlauf, RAM/CPU und UI-Reaktionszeit.
- [ ] LDAP/AD-Gruppenzuordnung, TLS-Zertifikate und SMTP-Versand in der tatsächlichen Air-Gap-Umgebung testen.
- [ ] Offline-Handbuch und portable Pakete final auf Zielsystemen prüfen.

### Priorität 3 — Qualität und Erweiterung
- [ ] Zusätzliche Muster-/Formatfälle und synthetische Testkorpora (IPv6, URL-Encoding, mehrzeilige Stacktraces, überlappende Regeln).
- [ ] CSV-/XML-Bereinigung fachlich entscheiden und bei Freigabe implementieren; derzeit nur Validierung.
- [ ] Performance bei vielen Regeln und typischen Anwendungslogs messen und gezielt optimieren.
- [ ] Release-Pakete, Versionierung und Changelog mit einem echten Testrelease prüfen.

## UI-Gestaltungsrichtlinien (bei Umsetzung der jeweiligen UI-Roadmap-Punkte)

Diese Richtlinien gelten verbindlich, werden aber schrittweise mit den jeweils anstehenden Oberflächen umgesetzt und ziehen keine späteren Roadmap-Arbeiten vor:

- Eine Bildschirmseite soll die für den aktuellen Arbeitsschritt nötigen Informationen und Aktionen möglichst vollständig zeigen; unnötiges seitenweites Scrollen vermeiden.
- Menüs und Reiter zur klaren Gliederung einsetzen.
- Dropdowns und Select-Listen Freitextfeldern vorziehen, wenn die Auswahlmenge bekannt und begrenzt ist.
- Pfade und Dateien über einen geeigneten Dateibrowser auswählen, nicht manuell in Textfelder eingeben.
- Mouseover-/Fokus-Hilfen und die Offline-Hilfe sollen die Bedienung verständlich erklären.
