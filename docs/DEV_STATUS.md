# Entwicklungsstand — Übergabe für den nächsten Chat

Stand: 2026-10-31
Repository: `Ineedat/ChatGPT`
Arbeitsbranch: `feature/project-management-sqlite`
Pull Request: [#2](https://github.com/Ineedat/ChatGPT/pull/2) — offen, nicht gemergt
Zuletzt bearbeiteter Commit: `de35c0536c8f4d5e072cc92a5fdc6e301e5b013c`

## Projektleitplanken

- LogSanitizer ist für einen eigenständigen Windows-/Linux-Laptop oder ein definiertes Air-Gap-Netz vorgesehen.
- Performance und Bedienbarkeit haben Vorrang; keine Rückkehr zu den verworfenen High-Security-Sonderanforderungen.
- Benutzerrollen, Berechtigungen, Review/Freigabe, Audit, Offline-Betrieb und unveränderte Quelldateien bleiben verbindlich.
- Backend: FastAPI/Python; Frontend: React/TypeScript; Metadaten/Mappings: SQLite.
- Große Logdateien werden gestreamt verarbeitet (Zielgröße mindestens 5 GiB).
- UI-Richtlinien aus der Roadmap schrittweise anwenden: möglichst wenig seitenweites Scrollen, passende Tabs/Menüs, Selects statt Freitext wo sinnvoll, Dateiauswahl statt manueller Pfadeingabe.

## Zuletzt abgeschlossene Arbeiten

1. Offline-Regelbibliothek mit 20 Startvorlagen in acht Kategorien.
2. Regeltest und synthetische Bereinigungsvorschau mit Treffer-/Konfliktanzeige und flüchtigem Mapping.
3. Dateibasierte Regelvorschau registrierter Text-/JSONL-Dateien in begrenzten Fenstern bis 65.536 Zeichen; Anfang/Ende/Vor-/Zurück-Navigation, zwei synchron vertikal scrollende Ansichten, unabhängige horizontale Scrollleisten und farbige Treffer-/Ersetzungsmarkierungen.
4. GUI-Import und -Export versionierter JSON-Regelkonfigurationen (Schema v1):
   - Export von Regeln und Quellprofilen, ohne projektbezogene Mapping-Daten.
   - Importdatei maximal 2 MiB.
   - Serverseitige Validierung über `POST /api/rules/config/validate`.
   - Importvorschau mit Schema-/Konfliktprüfung; ungültige/konfliktbehaftete Dateien nicht übernehmbar.
   - Explizite Übernahme in einen ungespeicherten Entwurf; Aktivierung erst nach separatem Speichern.
   - Abfrage vor dem Ersetzen ungespeicherter Änderungen.
   - Offline-Hilfe und Roadmap aktualisiert; Frontend-Test für Import/Export ergänzt.

## CI-/PR-Status

- Die vorherige Dateivorschau hatte einen vollständig erfolgreichen PR-CI-Lauf mit fünf Jobs, einschließlich Backend Ubuntu/Windows, Frontend und portable Windows/Linux.
- Für die letzten Import-/Export-Änderungen wurden mehrere Commits übertragen; letzter bekannter Commit ist `de35c053`.
- Für genau diesen letzten Stand war beim Abschluss des letzten Chats noch kein abgeschlossener CI-Lauf bestätigt. Daher Import/Export noch nicht als CI-verifiziert deklarieren.
- PR #2 ist offen und nicht gemergt.
- Vor weiteren Änderungen zuerst Branch-Head, PR-Status und neueste Push-/PR-Workflows prüfen. Fehlgeschlagene Jobs analysieren und beheben, bis alle relevanten Jobs grün sind.

## Nächste Schritte

1. CI für den aktuellen Branch-Head abwarten/prüfen und alle Fehler beheben.
2. Import-/Export-Tests und TypeScript-Build verifizieren; insbesondere Dateiauswahl, serverseitige Validierung, Konfliktfall, explizite Übernahme, Speichern und Export testen.
3. Danach Priorität 1 fortsetzen: vollständigen Projektablauf in der Oberfläche verbinden — Projekt, Dateien, Format, Quellprofil/Regeln, Bereinigung, Validierung und Freigabe.
4. Dabei die UI-Gestaltungsrichtlinien schrittweise auf die jeweils bearbeiteten Oberflächen anwenden.
5. Priorität 2 bleibt offen: E2E-Berechtigungstests der Regelverwaltung, Review-GUI, Zielsystem-Abnahme Windows/Linux, 5-GiB-Zielhardwaremessung, echte LDAP/SMTP-Integration und finales Offline-Handbuch/Paket-Testing.

## Wichtige Hinweise für die Fortsetzung

- Nicht mergen, solange CI oder die geforderte Zielumgebungs-Abnahme offen ist.
- Keine Migration alter Entwicklungs-Mappings einführen; produktive Nutzung startet mit frischen Daten.
- Die JSON-Regelkonfiguration enthält keine Projekt-Mappings.
- Die Dateivorschau darf nie die vollständige große Quelldatei in den Arbeitsspeicher laden.
