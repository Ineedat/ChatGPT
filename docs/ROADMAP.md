# Roadmap

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
- [x] Persistente projektbezogene Index-Mappings in separater lokaler SQLite-Datei; Originalwerte mit AES-256-GCM verschlüsselt, HMAC-Fingerprints für stabile Suche, separater zufälliger Schlüsseldatei, POSIX-Modus 0600/Verzeichnis 0700 bzw. explizite Windows-ACL für Schlüssel und Datenverzeichnis. Fehlender/falscher Schlüssel und manipulierte Chiffretexte werden fail-closed behandelt; Migration alter Klartextdatenbank und Backup-/Recovery-Tests sind implementiert. CI: vollständige Backend-Suite unter Linux (66 bestanden, 2 übersprungen) sowie Mapping-/ACL-/Recovery-Suite unter Windows (8 bestanden, 1 übersprungen). Manuelle Wiederherstellung auf den tatsächlich unterstützten Zielsystemen bleibt vor vertraulichem Einsatz erforderlich.
- [x] Fortschrittsanzeige und kooperativer Abbruch für Hintergrundläufe; Verarbeitung meldet Phase, Bytes und Zeilen.
- [x] Ausgabe wird in einer temporären Datei im Zielordner erzeugt, validiert und erst danach ohne Überschreiben veröffentlicht; temporäre Datei wird bei regulärem Erfolg, Fehler oder Abbruch entfernt.
- [x] Dauerhafte Lauf-/Prüfhistorie mit Ergebniskennzahlen, Status, Kommentaren, Ausnahmebegründungen und Audit-Ereignissen in einer separaten lokalen SQLite-Datenbank.
- [x] Dauerhafte Hintergrundjob-Status-/Fortschrittsdaten in SQLite; beim Start verwaiste Läufe als `interrupted` markieren und zugehörige verwaiste Staging-Dateien sicher bereinigen.
- [x] Pflichtvalidierung nach der Bereinigung: Ausgabe vollständig zeilenweise erneut lesen, UTF-8/JSONL-Syntax prüfen und alle aktiven konfigurierten Muster auf Resttreffer scannen; bei Fehlern Ausgabe löschen und Lauf ablehnen. Gilt nur für unterstützte Text-/JSONL-Ausgabe und ist kein Beweis vollständiger Geheimniserkennung.

## Meilenstein 2 — Prüfung und kontrollierte Freigabe
- [x] Lokale Anmeldung, serverseitige Rollenprüfungen und Login-Oberfläche; Authentifizierungs- und Regressionstests in CI erfolgreich.
- [x] Prüfer-Warteschlange und sichere wörtliche Stichprobensuche ausschließlich in bereinigten Ausgaben; eigene gespeicherte Suchmuster.
- [x] Freigabe, Rückgabe, Stopp und Kommentare; Laufhistorie und unveränderliche Audit-Ereignisse.
- [x] Eng begrenzte, ausdrücklich begründete Ausnahmen; fehlgeschlagene Pflichtvalidierungen bleiben nicht freigabefähig.
- [ ] Vollständige Sicherheitsprüfung der Authentifizierung/Rollenmatrix vor Produktions- oder Netzwerkbetrieb.

## Meilenstein 3 — Deployment
- [x] Optionale SMTP-Benachrichtigungen für ausstehende Prüffreigaben und zurückgegebene Läufe; Konfiguration über lokale Umgebungsvariablen und automatisierte Tests.
- [ ] Optionale LDAP/AD-Integration.
- [ ] Geschützte Darksite-Netzwerkbindung.
- [ ] Portable Windows-/Linux-Paketierung und Offline-Handbuch.
- [ ] Sicherheits- und Performanceprüfung, Testdateien >= 5 GB.

## Definition of done
Eine Funktion benötigt Tests, verständliche Offline-Hilfe, sicheres Fehlerverhalten und Dokumentation. Sicherheitsfunktionen müssen auch abgewiesene/unzulässige Pfade testen.
