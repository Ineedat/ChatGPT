# Entwicklungsstand — Übergabe für den nächsten Chat

Stand: 2026-11-04
Repository: `Ineedat/ChatGPT`
Arbeitsbranch: `feature/project-management-sqlite`
Pull Request: [#2](https://github.com/Ineedat/ChatGPT/pull/2) — offen, nicht gemergt
Letzter Code-Commit: `04047487e17a2aa6fe889771d65ef0516ee6b4c1`
Letzter Übergabe-/Dokumentationsstand: Bearbeitervergleich, Rückweisungsstatus und tabellarische Benutzerverwaltung umgesetzt; CI vollständig erfolgreich

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


## CI-Optimierung (2026-10-31)

- Die reguläre Push-/PR-CI wurde auf schnelle Prüfungen reduziert: Backend-Tests (Linux), gezielte Backend-Regressionsprüfungen (Windows), Ruff auf beiden Plattformen sowie Frontend-Tests und Build.
- Der kleine und vollständige synthetische Benchmark sowie die portablen Windows-/Linux-Builds wurden aus der regulären CI entfernt.
- Neuer manueller Workflow `.github/workflows/milestone-validation.yml`: 5-GiB-Benchmark (standardmäßig aktiv, optional deaktivierbar), portable Builds beider Betriebssysteme und Standalone-/HTTPS-Netzwerk-Smoke-Tests.
- Der bestehende tag-basierte Release-Workflow bleibt unverändert.
- Die neue Workflow-Aufteilung muss nach dem Commit noch durch die normale CI und einen manuell gestarteten Meilensteinlauf bestätigt werden.
- Anleitung: [docs/CI.md](CI.md).


## Projektworkflow-Navigation (2026-10-31)

- Das geöffnete Projekt bietet jetzt einen direkten Einstieg in die Regel- und Quellprofilverwaltung.
- Regelverwaltung und Prüfung/Verlauf bieten eine Rücknavigation in den Projektarbeitsbereich.
- Der direkte Sprung aus einem erfolgreich abgeschlossenen Bereinigungslauf in die Prüfung bleibt erhalten.
- Frontend-Regressionstests decken die Hin- und Rücknavigation ab.
- CI-Verifizierung des aktuellen Branch-Heads steht noch aus.


## UI-Fortsetzung (2026-10-31)

- Neuer kompakter UI-Grundstil auf Branch `feature/project-management-sqlite`: helle Windows-orientierte Farbpalette, Segoe UI, 10-px-Schrift, klare Rahmen und Fokusindikatoren.
- Bedienelemente, Karten, Abstände und Arbeitsbereiche wurden verdichtet; Warn-, Fehler- und Erfolgsmeldungen behalten unterscheidbare kontrastreiche Zustände.
- Visuelle Abnahme auf realen Windows-/Linux-Zielsystemen steht noch aus; nächster Implementierungsschritt ist die weitere Verdichtung des Projektarbeitsbereichs und der Dateiliste.
- CI für diesen UI-Stand muss noch vollständig durchlaufen.


## Projektarbeitsbereich — kompakte Dateikarten (2026-10-31)

- Registrierte Dateien werden in einem responsiven Kartenraster dargestellt.
- Status, Endungs-Hinweis, erkannter Typ und Dateigröße sind direkt sichtbar.
- Formatauswahl, Erkennung, vollständige Validierung, Quellprofil, Ausgabepfad und Bereinigung sind pro Datei kompakt gruppiert und ohne zusätzliche Menüs erreichbar.
- Die Bereinigungsaktion ist primär hervorgehoben und bleibt bei nicht unterstütztem Format oder fehlendem Ausgabepfad deaktiviert.
- Ein Frontend-Regressionstest prüft die Gruppierung und Sichtbarkeit der Aktionen.
- GitHub-CI für diesen Commit steht noch aus; die visuelle Prüfung auf Zielsystemen ist offen.


- Im geöffneten Projekt werden die allgemeinen Prinzipien-Karten ausgeblendet; sie bleiben nur in der Übersicht ohne ausgewähltes Projekt sichtbar. Dadurch steht mehr Bildschirmfläche für Dateiverwaltung und Verarbeitung zur Verfügung.


## Dateiimport — Bedienungsvereinheitlichung (2026-11-01)

- Einzeldatei und Ordner werden über ein gemeinsames Formular mit Auswahl des Quelltyps hinzugefügt.
- Eine gemeinsame Pfadeingabe, Ladeanzeige, Fehlerbehandlung und Statusmeldung reduziert doppelte UI-Logik.
- Die rekursive Option erscheint nur bei Ordnerimport; das Limit von 5.000 Kandidaten, Duplikaterkennung und Fehlerliste bleiben erhalten.
- Die Registrierung liest weiterhin keine Log-Inhalte und verändert keine Quelldateien.
- Noch offen: geeigneten lokalen Dateibrowser für Windows/Linux-Standalone und Air-Gap-Betrieb integrieren. Die aktuelle Pfadeingabe ist bis dahin ein technischer Zwischenschritt.
- CI für den Implementierungsstand steht noch aus.


## Lokaler Datei-/Ordnerbrowser und Upload (2026-11-01)

- Browser-Dateiauswahl für Mehrfachdateien und Ordner mit relativer Unterordnerstruktur ergänzt; manuelle Backend-Pfadeingabe bleibt als aufklappbarer Fallback.
- Upload-Endpunkt legt Dateien im Projektarbeitsbereich unter dem konfigurierten Datenverzeichnis ab und registriert sie erst nach vollständigem Kopieren.
- Backend liest Uploads in 1-MiB-Blöcken, begrenzt jede Datei auf 5 GiB und eine Auswahl auf 5.000 Dateien; unvollständige temporäre Dateien werden bei Fehlern entfernt.
- Relative Uploadpfade werden auf absolute Pfade, Laufwerkspräfixe und Traversal geprüft; Originaldateien auf dem Client werden nicht verändert.
- Regressionstests decken Upload, Ordnerstruktur, Traversal-Schutz und Größenlimit ab. CI-Verifizierung steht noch aus.


## Datei-/Ordnerauswahl — CI-Abschluss (2026-11-01)

- Implementiert: Browser-Dateiauswahl für Mehrfachdateien und Ordner, Übernahme der relativen Ordnerstruktur, blockweiser Upload in den Projektarbeitsbereich.
- Backend: Upload-Limit 5 GiB je Datei, 5.000 Dateien je Auswahl, 1-MiB-Kopierblöcke in einem Worker-Thread, temporäre Dateien mit atomarer Übernahme und Bereinigung bei Fehlern.
- Sicherheit/Integrität: relative Pfade werden gegen Traversal und Laufwerkspräfixe geprüft; Originaldateien im Browser bleiben unverändert. Uploads werden erst nach vollständiger Übernahme registriert.
- Offline-Hilfe und Fallback für bereits auf dem Backend vorhandene Pfade ergänzt.
- Regressionen: erfolgreicher Mehrdatei-Upload, verschachtelte Ordnerstruktur, Pfad-Traversal und Dateigrößenlimit.
- CI für Commit `3090d30aa304095dbe6f1666a258a7704b545325`, PR-Lauf [41291446536](https://github.com/Ineedat/ChatGPT/actions/runs/41291446536), vollständig erfolgreich: Frontend-Tests und Build, vollständige Backend-Suite unter Linux, gezielte Projekt-/Upload- und Mappingtests unter Windows sowie Ruff auf beiden Plattformen.
- PR #2 bleibt offen und ungemergt.
- Noch offen und nicht durch CI ersetzbar: visuelle Abnahme auf realen Windows-/Linux-Zielbildschirmen. Der separate manuelle Meilensteinlauf für portable Pakete und den 5-GiB-Benchmark wurde in diesem Schritt nicht gestartet.



## Speicherplatzprüfung beim Datei-/Ordnerupload (2026-11-01)

- Der Upload prüft vor dem ersten Kopiervorgang den freien Speicherplatz auf dem Zielvolume gegen die Gesamtgröße der ausgewählten Dateien.
- Zusätzlich wird eine Sicherheitsreserve von mindestens 16 MiB bzw. 5 % der Uploadgröße verlangt.
- Bei zu wenig Speicherplatz wird die gesamte Auswahl mit HTTP 507 abgelehnt; es werden keine Dateien teilweise übernommen.
- Unmittelbar vor jeder einzelnen Datei erfolgt eine erneute Prüfung, damit zwischenzeitlich belegter Speicher erkannt wird.
- Die Prüfung läuft serverseitig auf dem tatsächlichen Zielvolume und funktioniert damit für Windows- und Linux-Zielsysteme.
- Regressionstests decken die Gesamtprüfung und einen zwischenzeitlichen Rückgang des freien Speicherplatzes ab; CI-Verifizierung steht noch aus.



## Mehrdatei-Projektworkflow (2026-11-01)

- Projektdateien können im Arbeitsbereich einzeln oder gesammelt für einen Stapellauf ausgewählt werden.
- Die ausgewählten Dateien werden nacheinander über die bestehenden dauerhaften Einzeldatei-Jobs verarbeitet. Damit bleiben Jobstatus, Fortschritt, Abbruch, Pflichtvalidierung, Audit und Review pro Datei unabhängig.
- Quellprofil und Ausgabepfad werden weiterhin pro Datei festgelegt. Vor dem Start prüft die UI, dass alle ausgewählten Dateien ein unterstütztes Format und einen eigenen Ausgabepfad besitzen; doppelte Ausgabeziele werden abgewiesen.
- Ein Stapelabbruch fordert den kooperativen Abbruch der aktiven Datei an und verhindert den Start weiterer Dateien.
- Die projektbezogene SQLite-Mapping-Tabelle wird von jedem Job mit derselben Projekt-ID verwendet; derselbe Originalwert erhält daher dateiübergreifend denselben Platzhalter. Der Backend-Regressionstest `test_indexed_mapping_is_stable_across_files_and_isolated_by_project` deckt dies ab.
- Frontend-Tests prüfen die sequentielle Reihenfolge (Datei 2 startet erst nach dem terminalen Status von Datei 1) sowie die Abweisung doppelter Ausgabepfade.
- CI-Verifizierung des Mehrdatei-Frontend- und Dokumentationsstands ist mit Push-Lauf [41324254157](https://github.com/Ineedat/ChatGPT/actions/runs/41324254157) und PR-Lauf [41324257605](https://github.com/Ineedat/ChatGPT/actions/runs/41324257605) vollständig abgeschlossen; alle drei Jobs waren erfolgreich.



## Mehrdatei-Projektworkflow — CI-Abschluss (2026-11-01)

- Code-Commit: `cf5e14896b6b7310b9be0d6a0cd61d2d08772ff1`.
- Push-CI [41324254157](https://github.com/Ineedat/ChatGPT/actions/runs/41324254157) und PR-CI [41324257605](https://github.com/Ineedat/ChatGPT/actions/runs/41324257605) vollständig erfolgreich; jeweils Frontend, Backend Linux und Backend Windows grün.
- Frontend: 31 Tests erfolgreich; TypeScript-/Vite-Produktionsbuild erfolgreich.
- Backend Linux: 110 passed, 1 skipped; Ruff ohne Befund.
- Backend Windows: 20 gezielte Projekt-/Mappingtests erfolgreich; Ruff ohne Befund.
- Projektweite Mapping-Konsistenz wird durch `test_indexed_mapping_is_stable_across_files_and_isolated_by_project` abgesichert.
- Mehrdatei-Frontendtests bestätigen, dass die zweite Datei erst nach dem terminalen Status der ersten gestartet wird und doppelte Ausgabepfade vor dem Start erkannt werden.
- PR #2 bleibt offen und ungemergt.


## Relative Ausgabepfade und tabellarische Dateiverwaltung (2026-11-01)

- SQLite-Schema Version 5 speichert den relativen Quellpfad je registrierter Datei. Browser-Uploads und Ordnerimporte bewahren damit Unterordner und erlauben gleiche Dateinamen in unterschiedlichen Quellordnern.
- Dateien aus dem Backend-Pfad-Fallback erhalten als relativen Pfad ihren Dateinamen; absolute Quellpfade werden nicht an die Oberfläche ausgegeben.
- Bereinigungsjobs müssen im konfigurierten Projekt-Ausgabeordner und unter dem gespeicherten relativen Quellpfad schreiben. Fehlende Unterordner werden automatisch erstellt; vorhandene Ausgabedateien werden nicht überschrieben. Symlink-/Traversal-Ausbrüche aus dem Ausgabeordner werden abgewiesen.
- Die Dateikarten wurden durch eine kompakte Tabelle ersetzt. Format, Quellprofil, Validierungsstatus, Bereinigungsstatus und zeilenbezogene Aktionen sind direkt sichtbar und bedienbar.
- „Gemeinsame Einstellungen“ wendet Format und Quellprofil auf alle registrierten Dateien des Projekts an.
- Formatänderung und erneute Erkennung setzen einen zuvor ermittelten Validierungsstatus zurück, damit keine veraltete Gültigkeitsanzeige bestehen bleibt.
- Offline-Hilfe aktualisiert; Regressionen decken relative Pfade, gleiche Basenames in verschiedenen Unterordnern, Dateitabelle und die neuen Ausgabeordnerregeln ab.
- CI für Commit `75a81ac31a23`, Lauf [41341831979](https://github.com/Ineedat/ChatGPT/actions/runs/41341831979), vollständig erfolgreich:
  - Frontend: 31 Tests und Produktionsbuild erfolgreich.
  - Backend Linux: 118 passed, 1 skipped; Ruff erfolgreich.
  - Backend Windows: 23 gezielte Projekt-/Mappingtests; Ruff erfolgreich.
- PR #2 bleibt offen und nicht gemergt. Das portable Linux-Paket wurde für diesen Stand noch nicht neu gebaut; die visuelle Abnahme auf dem Zielsystem steht weiterhin aus.


## Prüfarbeitsbereich, Quellprofile und Benutzeranlage (2026-11-01)

- Quellprofile werden nun einzeln und unmittelbar gespeichert: Anlegen, Bearbeiten und Löschen validieren die vollständige Regelkonfiguration serverseitig und schreiben sie erst nach erfolgreicher Prüfung. Nicht gespeicherte Regeländerungen blockieren das separate Profilspeichern, damit sie nicht unbeabsichtigt mit aktiviert werden.
- Die Prüfansicht lädt die registrierten Dateien des aktuell geöffneten Projekts und zeigt pro Datei den letzten Bereinigungslauf und dessen Status.
- Für prüfbare Läufe kann der Prüfer einen Dateivergleich öffnen. Original und sanitisierte Ausgabe werden nebeneinander in getrennten, scrollbar begrenzten Fenstern mit jeweils maximal 65.536 Byte angezeigt. Vor-/Zurücknavigation erfolgt fensterweise; die gesamte Datei wird nicht in den Arbeitsspeicher geladen.
- Der neue Vergleichsendpunkt ist auf Administratoren, Prüfer und Freigeber beschränkt. Er prüft vor der Anzeige die gespeicherte Identität der sanitisierte Ausgabe und gibt keine absoluten Dateipfade zurück.
- Warteschlange, Dateiprüfung und Prüfverlauf sind jetzt getrennte Ansichten innerhalb der Prüfoberfläche. Das Audit-Protokoll befindet sich im Prüfverlauf.
- Die Benutzerverwaltung zeigt die Anlage nicht mehr inline in der Benutzerliste. „Neuen Benutzer anlegen“ öffnet eine separate Ansicht; nach erfolgreicher Anlage kehrt die Oberfläche zur Liste zurück.
- Regressionstests ergänzt: Quellprofil anlegen/bearbeiten, separate Benutzeranlage, Projektdateiliste und Dateivergleich, rollenbeschränkter Vergleichsendpunkt sowie Navigation über große Dateien.
- Die Änderungen dieses Abschnitts wurden im CI-Lauf [41677942384](https://github.com/Ineedat/ChatGPT/actions/runs/41677942384) vollständig erfolgreich geprüft; Details siehe Stabilisierung vom 2026-11-03.


## Review-Arbeitsbereich und Quellprofile — Stabilisierung (2026-11-03)

- Vergleichsansicht: vertikales Scrollen der Original- und Ausgabeansicht wieder synchronisiert; horizontales Scrollen bleibt bewusst unabhängig.
- Asynchrone Vergleichsabfragen erhalten eine Sequenzkennung. Später gestartete Anfragen können nicht mehr durch verspätete Antworten älterer Dateiauswahlen überschrieben werden.
- Kontrast der Prüfansicht, Eingabefelder und Vergleichsfenster auf helle Windows-orientierte Flächen mit dunkler Schrift festgelegt; Fundstellen und Ersetzungen bleiben gelb bzw. grün hervorgehoben.
- Freigegebene Dateien werden in der Projektdateiliste ausdrücklich als „Freigegeben · gesperrt“ gekennzeichnet. Der Sperrhinweis erklärt, dass Formatänderung, erneute Erkennung und weitere Bereinigung blockiert sind; die Vergleichsansicht bleibt für freigegebene Läufe verfügbar.
- Quellprofilverwaltung: bestätigtes Verwerfen eines offenen Regelentwurfs setzt den Entwurf tatsächlich zurück. Eine eigene Aktion verwirft sämtliche ungespeicherten Konfigurationsänderungen und lädt den gespeicherten Stand neu.
- Regressionstests prüfen Quellprofil-Anlage, Bearbeitung, Löschung, Schutz verwendeter Profile sowie die getrennte Speicherung nach Verwerfen eines Regelentwurfs.
- Vergleichsregressionen prüfen vertikale Synchronisierung und unabhängige horizontale Navigation; Freigabestatus und Sperrhinweis sind ebenfalls abgedeckt.
- CI-Lauf [41677942384](https://github.com/Ineedat/ChatGPT/actions/runs/41677942384) vollständig erfolgreich:
  - Frontend: 38 Tests erfolgreich; TypeScript-/Vite-Produktionsbuild erfolgreich.
  - Backend Linux: 122 passed, 1 skipped; Ruff ohne Befund.
  - Backend Windows: 23 gezielte Projekt-/Mappingtests passed; Ruff ohne Befund.
- PR #2 bleibt offen und ungemergt. Die visuelle Abnahme auf echter Windows-/Linux-Zielhardware sowie die Air-Gap-Integration mit LDAP/AD, TLS und SMTP bleiben externe Abnahmepunkte.


## Bearbeitervergleich und tabellarische Benutzerverwaltung (2026-11-04)

- Bearbeiter sehen zurückgewiesene Läufe in der Projektdateiliste ausdrücklich als „Zurückgewiesen – Überarbeitung erforderlich“ einschließlich Rückgabegrund.
- Der Dateivergleich steht Bearbeitern für eigene Läufe zur Verfügung. Die Backend-Route prüft die Laufzugehörigkeit; Vergleiche fremder Läufe bleiben für Bearbeiter gesperrt. Die zentrale Auth-Middleware gibt ausschließlich GET-Anfragen auf den Vergleichsendpunkt frei.
- Vergleichsfenster verwenden die bestehende begrenzte Original-/Ausgabeansicht mit synchronem vertikalem und unabhängigem horizontalem Scrollen sowie farbigen Fund-/Ersetzungsmarkierungen.
- Die Benutzerverwaltung zeigt vorhandene Konten tabellarisch mit Benutzername, Kontotyp, Aktivstatus, Rollen und Aktionen; Anlage bleibt eine separate Ansicht.
- Regressionen ergänzen Backend-Berechtigungsprüfung und Frontend-Anzeige/Interaktion.
- CI-Lauf [41913563076](https://github.com/Ineedat/ChatGPT/actions/runs/41913563076) vollständig erfolgreich: Frontend 39 Tests und Produktionsbuild; Backend Linux 122 passed, 1 skipped; Backend Windows 23 Tests; Ruff auf beiden Plattformen.
- PR #2 bleibt offen und ungemergt. Zielsystem-Abnahme sowie LDAP/AD, TLS und SMTP in der tatsächlichen Air-Gap-Umgebung sind weiterhin offen.

## LDAP-Anmeldung und Backend-Konfigurationshilfe (2026-11-04)

- Tatsächlichen PR-Branch-Stand zu Beginn geprüft: PR #2 offen, Branch `feature/project-management-sqlite`; die Übergabe vom 04.11. bleibt die maßgebliche Projektbasis.
- LDAP-Passwortanmeldung im vorhandenen Backend geprüft: Das Passwort aus dem normalen LogSanitizer-Anmeldeformular wird bereits als persönliches LDAP-/AD-Benutzerpasswort für den Bind mit dem gefundenen Benutzer-DN verwendet. Ein persönliches Client-Zertifikat ist dafür nicht erforderlich.
- Das bisherige Konfigurationsverständnis wurde in der Oberfläche korrigiert: Die Loginseite spricht nun ausdrücklich lokale Konten und LDAP-/Active-Directory-Konten an und weist auf das persönliche Verzeichnispasswort hin.
- Neue ausführliche Offline-Hilfe `Backend-Konfiguration: LDAP/AD, TLS und SMTP` ergänzt. Sie erklärt den LDAP-Anmeldeablauf, den Unterschied zwischen persönlichem Benutzerpasswort und technischem Suchkonto-Passwort, LDAPS/StartTLS, CA- und HTTPS-Zertifikate, Benutzerfilter, Suchbasis, Gruppenattribute, Rollen-DNs, SMTP und die relevanten Umgebungsvariablen.
- `docs/DEPLOYMENT.md` um eine ausführliche Backend-Konfigurationsreferenz mit LDAP-/AD-Beispielprofil, SMTP-Beispiel, Feldtabelle und Inbetriebnahme-/Fehlersuchcheckliste erweitert.
- Wichtige Klarstellung: `LOGSANITIZER_LDAP_BIND_PASSWORD` ist das Passwort des technischen Suchkontos (`ldap.bind_dn`), nicht das Passwort des Mitarbeiters. Das persönliche LDAP-Passwort wird bei jeder Anmeldung im Passwortfeld eingegeben. `ldap.ca_certs_file` ist eine CA-Datei zur Serverzertifikatsprüfung, kein persönliches Benutzerzertifikat.
- Die bestehende LDAP-Implementierung bindet nach der Benutzersuche separat mit dem eingegebenen Benutzerpasswort. Der bestehende Regressionstest `test_network_login_uses_ldap_only_and_sets_secure_cookie` deckt den Passwortpfad auf API-Ebene mit simuliertem LDAP ab.
- Neue Commits auf dem Arbeitsbranch: `d9261c4` (Offline-Hilfe), `d2003e1` (Deployment-Dokumentation), `e48905b` (Login-Hinweis) und `b647727` (Korrektur eines Help-Text-Syntaxdetails).
- CI-Verifizierung dieser Dokumentations-/UI-Änderungen steht noch aus. GitHub lieferte für den zuletzt geprüften Commit keine Statuschecks bzw. Workflow-Runs zurück; die Änderungen dürfen daher noch nicht als CI-grün bezeichnet werden.
- PR #2 bleibt offen und ungemergt. Reale LDAP-/AD-, TLS- und SMTP-Abnahme im Air-Gap-Netz bleibt weiterhin erforderlich.

## Ergänzung: LDAP-Bind-Regression und Backend-Kurzanleitung (2026-11-04)

- Zusätzliche Backend-Regression `backend/tests/test_ldap_auth.py`: prüft getrennt den Bind des technischen Suchkontos mit `LOGSANITIZER_LDAP_BIND_PASSWORD` und den anschließenden Benutzer-Bind mit dem persönlichen Passwort aus dem Loginformular. Ein falsches persönliches Passwort muss abgewiesen werden.
- `backend/README.md` vollständig überarbeitet: veraltete und widersprüchliche Hinweise entfernt; kompakte Start-, Deployment-, LDAP-Passwort- und Geheimnis-Konfiguration ergänzt; Verweis auf die ausführliche Deployment-Referenz hinzugefügt.
- Der Loginbildschirm nennt nun ausdrücklich lokale und LDAP-/Active-Directory-Konten. Die Offline-Hilfe erklärt außerdem, dass `ldap.ca_certs_file` eine CA-Datei für das LDAP-Serverzertifikat ist und kein persönliches Benutzerzertifikat.
- Letzter Commit dieses Arbeitsschritts: `923468b93fa8827afc1035a6e09da89c6011455a`.
- PR #2 bleibt offen und ungemergt. Für die neuen Änderungen liegen aktuell noch keine abrufbaren CI-Statuschecks oder Workflow-Runs vor; Tests sind daher noch nicht als ausgeführt/erfolgreich zu deklarieren.
- Test-Fixture nach Review korrigiert: die simulierten `ldap3`-Module werden als importierbares Paket registriert. Letzter Test-Commit: `0bdcb81cbddf5fc02f05f6b5042d983f4434dced`.


## LDAP-/Frontend-Nachprüfung (2026-11-04)

- Die Login-Oberfläche erklärt nun ausdrücklich, dass im LDAP-/AD-Modus das persönliche Verzeichnispasswort eingegeben wird. Das technische Suchkonto bleibt davon getrennt und wird ausschließlich über `LOGSANITIZER_LDAP_BIND_PASSWORD` bereitgestellt.
- Die Offline-Hilfe für LDAP/AD, LDAPS, StartTLS, CA-Zertifikat, HTTPS-Serverzertifikat, Gruppen-/Rollenzuordnung und SMTP wurde ergänzt.
- Bei der Nachprüfung wurde ein fehlendes Komma zwischen zwei Hilfeeinträgen in `frontend/src/help/content.ts` gefunden und behoben (Commit `1ebf2c8`).
- Die Meilenstein-Workflow-Datei wurde mit der aktuellen Version aus `main` synchronisiert. Damit ist die in `main` vorgenommene Auswahl des zu prüfenden Feature-Branches auch im PR-Branch vorhanden (Commit `230316e`).
- LDAP-Regressionstests decken nun zusätzlich die Reihenfolge StartTLS-vor-Bind sowie das Escaping von Benutzereingaben im LDAP-Suchfilter ab (Commits `dde7d80`, `23a964a`, `780218e`).
- PR #2 bleibt offen. GitHub meldet den aktuellen PR-Stand als mergebar; der Branch liegt im Commitvergleich weiterhin vier Commits hinter `main`, enthält aber die aktuelle Meilenstein-Workflow-Datei.
- **Wichtig: Für den aktuellen Head `780218e` wurden über die verfügbaren GitHub-Abfragen keine Statuschecks und keine zugehörigen PR-Workflow-Runs zurückgegeben.** Die zuletzt dokumentierten grünen CI-Läufe beziehen sich auf ältere Commits und dürfen nicht als Nachweis für diesen Stand verwendet werden. Frontend-Build, vollständige Backend-Tests/Ruff und portable Windows-/Linux-Smoke-Tests sind für diesen Head daher noch nicht bestätigt.
- Ein manueller Workflow-Dispatch ist über die derzeit verfügbare GitHub-Aktion nicht möglich. Vor dem Merge muss ein tatsächlicher CI-Lauf auf dem aktuellen Head mit allen erforderlichen Jobs grün vorliegen. Die reale LDAP-/AD-/SMTP-Abnahme sowie Zielhardwaretests bleiben zusätzlich externe Abnahmepunkte.


## CI-Abschluss LDAP-/Hilfe-Nachprüfung (2026-11-04)

- Nach dem ersten CI-Lauf wurde der Ruff-Befund `RUF012` im LDAP-Testfixture behoben: Das veränderliche Klassenattribut ist jetzt als `ClassVar` annotiert (Commit `36cd31f`).
- CI-Lauf [#41917400304](https://github.com/Ineedat/ChatGPT/actions/runs/41917400304) für den aktuellen Head `36cd31f5108b5c9391ac4bc0a1607c5df2fbc762` vollständig erfolgreich:
  - Linux-Backend: 126 passed, 1 skipped; Ruff erfolgreich.
  - Windows-Backend: 23 passed; Ruff erfolgreich.
  - Frontend: Vitest und TypeScript-/Vite-Build erfolgreich.
- Es verbleiben nicht-blockierende Deprecation-Warnungen (FastAPI/Starlette, Node-Abhängigkeit und GitHub-Actions-Runtime). Kein CI-Job ist fehlgeschlagen.
- PR #2 ist offen, nicht gemergt und wird von GitHub als mergebar gemeldet. Der Feature-Branch liegt im Commitvergleich weiterhin vier Commits hinter `main`; die abweichende Meilenstein-Workflow-Datei wurde inhaltlich mit `main` synchronisiert.
- Nicht durch diesen CI-Lauf abgedeckt: manueller Meilensteinlauf mit portablem Windows-/Linux-Paket und 5-GiB-Benchmark sowie reale LDAP-/AD-/SMTP-Verbindung und visuelle/Leistungsmessung auf der Zielhardware. Die zuvor dokumentierten 5-GiB-Ergebnisse beziehen sich auf ältere, bereits erfolgreich geprüfte Implementierungsstände.
- **Merge-Entscheidung:** Der aktuelle Code-CI-Stand ist grün. Ob vor dem Merge zusätzlich die reale Air-Gap-/Zielhardware-Abnahme verlangt wird, bleibt eine fachliche Freigabeentscheidung; diese Tests dürfen nicht als bereits erfolgt dargestellt werden.
