# Entwicklungsstand — Übergabe für den nächsten Chat

Stand: 2026-10-31
Repository: `Ineedat/ChatGPT`
Arbeitsbranch: `feature/project-management-sqlite`
Pull Request: [#2](https://github.com/Ineedat/ChatGPT/pull/2) — offen, nicht gemergt
Letzter Code-Commit: `c98bf5f878849cb1ec978edbd9e98578c6940e66`
Letzter Übergabe-/Dokumentationsstand: Dokumentation wird mit der aktuellen Regex-Such-Erweiterung aktualisiert

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

## Fortsetzung nach erfolgreichem CI-Lauf

- CI-Lauf `41227523826` für Commit `c0482d0` ist vollständig erfolgreich: Frontend-Tests/Build, Backend Linux, Backend Windows (gezielter Mapping-Test), portable Linux und portable Windows.
- Der Linux-Backend-Job hat auch den vollständigen synthetischen 5-GiB-Benchmark erfolgreich ausgeführt. Der Windows-Backend-Job überspringt den 5-GiB-Lauf weiterhin; der dedizierte Zielhardwaretest bleibt offen.
- In der Review-Oberfläche wurde eine Lücke behoben: Bei zurückgegebenen Läufen kann der Operator nun das Quellprofil erneut auswählen. Die Auswahl wird als `profile_id` an den neuen Bereinigungslauf übergeben; ohne Auswahl gelten globale Regeln.
- Offline-Hilfe und Roadmap wurden um den Review-/Überarbeitungsablauf ergänzt.
- Neue Frontend-Tests prüfen die Quellprofilwahl bei Überarbeitungen. Der erste CI-Lauf auf Zwischenstand `fd4bcbb` schlug wegen eines versehentlich als Text eingefügten `\\n`-Zeichens im neuen Hilfeeintrag fehl (Frontend-Test und portabler Linux-Build). Das Literal wurde in `7c5f745` korrigiert; CI für Commit `6c64e3c` (PR-Lauf `41228104875`) ist vollständig erfolgreich: alle fünf Jobs grün, einschließlich Linux-5-GiB-Benchmark und portabler Windows-/Linux-Smoke-Tests.

## Aktuelle Fortsetzung: Prüfer-Stichprobensuche

- Wörtliche Ad-hoc-Suche wurde um einen auswählbaren Regex-Modus ergänzt.
- Regex-Suche verwendet das bereits eingesetzte `regex`-Paket mit 100-ms-Zeitlimit je Zeile; maximale Zeilenlänge bleibt 1 MiB und es werden höchstens 20 Treffer ausgegeben.
- Gespeicherte Suchmuster speichern nun zusätzlich `match_type`; bestehende SQLite-Datenbanken erhalten beim Start eine additive Spalte mit Standardwert `literal`.
- Frontend-Auswahl für wörtlich/Regex, Anzeige der Suchart und Wiederherstellung beim Laden gespeicherter Muster ergänzt.
- Backend- und Frontend-Regressionstests hinzugefügt. Der neue Stand ist noch nicht CI-verifiziert.

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

1. CI des aktuellen Branch-Heads für die Regex-Such-Erweiterung vollständig abwarten und mögliche Fehler anhand der Logs beheben, bis alle fünf Jobs grün sind.
2. Besonders prüfen: Backend-Regex-/Saved-Search-Tests, Frontend-Regex-Test, TypeScript-Build und portable Windows-/Linux-Builds.
3. Priorität 1 fortsetzen: den vollständigen Projektablauf in der Oberfläche abschließen — Projekt, Dateien, Format, Quellprofil/Regeln, Bereinigung, Validierung und Freigabe. Die Quellprofil-Auswahl und der direkte Review-Link sind jetzt ergänzt; der vollständige End-to-End-Ablauf ist noch nicht abgenommen.
4. UI-Gestaltungsrichtlinien schrittweise auf die jeweils bearbeiteten Oberflächen anwenden; insbesondere manuelle Pfadeingaben später durch eine geeignete Dateiauswahl ersetzen, wenn dies für Standalone und Air-Gap-Betrieb sauber gelöst ist.
5. Priorität 2 bleibt offen: E2E-Berechtigungstests der Regelverwaltung, Review-GUI, Zielsystem-Abnahme Windows/Linux, 5-GiB-Zielhardwaremessung, echte LDAP/SMTP-Integration und finales Offline-Handbuch/Paket-Testing.

## Wichtige Hinweise für die Fortsetzung

- Nicht mergen, solange CI oder die geforderte Zielumgebungs-Abnahme offen ist.
- Keine Migration alter Entwicklungs-Mappings einführen; produktive Nutzung startet mit frischen Daten.
- Die JSON-Regelkonfiguration enthält keine Projekt-Mappings.
- Die Dateivorschau darf nie die vollständige große Quelldatei in den Arbeitsspeicher laden.


## Aktueller Stand der Fortsetzung (2026-10-31)

- Prüfer-Stichprobensuche: wörtlich/Regex, eigene gespeicherte Muster mit Suchart und 100-ms-Regex-Zeitlimit je Zeile.
- Prüferoberfläche erweitert: Laufhistorie nach Suchtext und Status filterbar; Vorgänger-/Folgeläufe navigierbar; Audit-Protokoll auf ausgewählten Lauf einschränkbar.
- Backend-Berechtigungsregression ergänzt: Administrator und Rule Owner dürfen Regelkonfiguration speichern; Processor wird beim Speichern, Validieren und Vorschau-Endpunkt abgewiesen.
- Frontend-Regression für Historienfilter und Laufketten ergänzt; Offline-Hilfe und Roadmap aktualisiert.
- CI für Code-Commit `d089e66205198ba9980164efb919e99707f633aa` (PR-Lauf [41228725651](https://github.com/Ineedat/ChatGPT/actions/runs/41228725651)) vollständig erfolgreich: alle fünf Jobs grün; Linux-Backend-Suite, Ruff, Frontend-Tests/Build, portable Windows-/Linux-Builds und Smoke-Tests. Der Linux-5-GiB-Benchmark war Teil des Linux-Backend-Jobs.
- PR #2 bleibt offen. Noch nicht abschließbare Abnahmepunkte erfordern Zugriff auf die tatsächliche Windows-/Linux-Zielhardware und die echte Air-Gap-Umgebung (LDAP/AD, TLS-Zertifikate, SMTP); diese dürfen nicht durch CI-Simulation als erledigt markiert werden.

## Nächste Schritte

1. Aktuelle CI des neuen Heads nach den Review-Historien- und Berechtigungsänderungen vollständig prüfen und Fehler beheben.
2. Bei grüner CI ist der implementierbare Teil des Review-/Freigabe-Meilensteins abgeschlossen.
3. Für den vollständigen Meilensteinabschluss anschließend die reale Zielsystem- und Air-Gap-Abnahme durchführen; Ergebnisse und Messwerte in `docs/PERFORMANCE.md` und `docs/DEV_STATUS.md` dokumentieren.


## CI-Abschluss Review-/Freigabe-Meilenstein (2026-10-31)

- Aktueller Code-Stand vor dieser Dokumentationsaktualisierung: `781a9af7a83af8dfb09c57b96a3501aa475cf4b1`.
- Der erste Lauf `41229407081` deckte einen Fehler im Berechtigungs-Test-Setup auf: Der gemeinsame Testclient verwendete nach dem Rollenwechsel weiterhin sein initiales CSRF-Token. Der Test setzt jetzt das CSRF-Token des jeweils angemeldeten Testbenutzers.
- Korrigierter PR-CI-Lauf [41229528527](https://github.com/Ineedat/ChatGPT/actions/runs/41229528527) vollständig erfolgreich: alle fünf Jobs grün (Linux-/Windows-Backend, Frontend, portable Linux-/Windows-Pakete einschließlich Netzwerk-Smoke-Tests).
- Backend: 105 passed, 1 skipped; Ruff erfolgreich. Frontend-Tests und Build erfolgreich.
- Vollständiger synthetischer 5-GiB-Benchmark erfolgreich: 97,621 s, 52,45 MiB/s, CPU 94,436 s, maximaler Prozess-RSS 40.148.992 Byte; 10.485.760 Zeilen und Ersetzungen; `validated=true`.
- Implementierbarer Teil des Review-/Freigabe-Meilensteins ist abgeschlossen. Die reale Zielsystem- und Air-Gap-Abnahme bleibt als externe Freigabevoraussetzung offen.
