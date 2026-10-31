# Entwicklungsstand — Übergabe für den nächsten Chat

Stand: 2026-10-31
Repository: `Ineedat/ChatGPT`
Arbeitsbranch: `feature/project-management-sqlite`
Pull Request: [#2](https://github.com/Ineedat/ChatGPT/pull/2) — offen, nicht gemergt
Letzter Code-Commit: `90f02701e94dc7bf2776a880bc9b451ae31abcca`
Letzter Übergabe-/Dokumentationsstand: nach diesem Commit aktualisiert

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
5. Projektworkflow weiter verbunden:
   - Quellprofile können je registrierter Datei über eine Select-Liste gewählt werden; Profilnamen werden bei Bedarf aus der Regelkonfiguration geladen.
   - Die Auswahl wird als `profile_id` an den Bereinigungslauf übergeben; ohne Auswahl gelten globale Regeln.
   - Nach erfolgreichem Lauf führt eine Schaltfläche direkt zu „Prüfung & Verlauf“.
   - Offline-Hilfe erklärt die Profilwahl; Hinweistext nennt UTF-8-Text, JSON Lines und vollständige JSON-Dokumente korrekt.

## CI-/PR-Status

- PR #2 ist offen und nicht gemergt.
- Der dokumentierte Branch-Head `de35c053` war veraltet; beim Start dieser Fortsetzung lag der tatsächliche Head bereits auf `e96669d`.
- CI für `e96669d` (Run `41145030425`) schlug fehl:
  - Frontend-Build: fehlendes Komma in `frontend/src/help/content.ts`.
  - Frontend-Tests: Import-/Export-Test griff vor Abschluss des initialen Ladens auf das Dateifeld zu; zusätzlich war der URL-Mock nicht sauber isoliert.
- Diese Punkte wurden korrigiert. Ein Zwischenlauf (`41227265389`) deckte zusätzlich einen versehentlich als Literal eingefügten `\\n`-Text im neuen App-Test auf; auch dieser Syntaxfehler wurde korrigiert.
- Der aktuelle Code-Head `90f0270` hat PR-CI-Lauf [41227434969](https://github.com/Ineedat/ChatGPT/actions/runs/41227434969). Beim letzten Abruf war dieser Lauf noch ausstehend und es waren noch keine Jobs gelistet. **Die Korrekturen und die neue Profilworkflow-Funktion sind daher noch nicht CI-verifiziert.**
- Nach dem letzten Code-Commit wurde diese Übergabedatei aktualisiert; dadurch kann ein weiterer CI-Lauf entstehen. Immer den tatsächlichen Branch-Head prüfen und nur den neuesten Lauf bewerten.

## Nächste Schritte

1. CI des aktuellen Branch-Heads vollständig abwarten und alle fehlgeschlagenen Jobs anhand ihrer Logs beheben, bis alle fünf Jobs grün sind.
2. Besonders prüfen: Frontend-Import-/Export-Tests, URL-Mock-Isolation, den neuen Quellprofil-Test, TypeScript-Build und portable Windows-/Linux-Builds.
3. Priorität 1 fortsetzen: den vollständigen Projektablauf in der Oberfläche abschließen — Projekt, Dateien, Format, Quellprofil/Regeln, Bereinigung, Validierung und Freigabe. Die Quellprofil-Auswahl und der direkte Review-Link sind jetzt ergänzt; der vollständige End-to-End-Ablauf ist noch nicht abgenommen.
4. UI-Gestaltungsrichtlinien schrittweise auf die jeweils bearbeiteten Oberflächen anwenden; insbesondere manuelle Pfadeingaben später durch eine geeignete Dateiauswahl ersetzen, wenn dies für Standalone und Air-Gap-Betrieb sauber gelöst ist.
5. Priorität 2 bleibt offen: E2E-Berechtigungstests der Regelverwaltung, Review-GUI, Zielsystem-Abnahme Windows/Linux, 5-GiB-Zielhardwaremessung, echte LDAP/SMTP-Integration und finales Offline-Handbuch/Paket-Testing.

## Wichtige Hinweise für die Fortsetzung

- Nicht mergen, solange CI oder die geforderte Zielumgebungs-Abnahme offen ist.
- Keine Migration alter Entwicklungs-Mappings einführen; produktive Nutzung startet mit frischen Daten.
- Die JSON-Regelkonfiguration enthält keine Projekt-Mappings.
- Die Dateivorschau darf nie die vollständige große Quelldatei in den Arbeitsspeicher laden.
