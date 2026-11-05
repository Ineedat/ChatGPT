# Technische Sicherheits- und Abnahmematrix – LogSanitizer

**Dokument-ID:** LS-SEC-002  
**Version:** 1.0  
**Stand:** 05.11.2026  
**Bezug:** [Sicherheitskonzept LS-SEC-001](SICHERHEITSKONZEPT.md), Anforderungen v2.8  
**Status:** Arbeits- und Abnahmeliste; Betreiberabnahme noch offen

## 1. Zweck und Verwendung

Diese Matrix übersetzt die Sicherheitsziele aus LS-SEC-001 in konkrete Prüfungen. Sie dient als gemeinsamer Nachweisplan für Entwicklung, Test und Betreiberabnahme.

Die Statusangaben beschreiben den dokumentierten Projektstand und nicht automatisch einen aktuell erfolgreich ausgeführten Testlauf:

- **Test vorhanden:** Im Repository existiert ein passender automatisierter Test. Vor einer Freigabe muss der zugehörige CI-Lauf erfolgreich sein.
- **Teilweise:** Ein Teilaspekt wird automatisiert geprüft; die vollständige Anforderung ist dadurch nicht nachgewiesen.
- **Offen:** Es fehlt ein ausreichender automatisierter oder realer Abnahmenachweis.
- **Betreiberprüfung:** Die Prüfung muss in der konkreten Zielumgebung durchgeführt und protokolliert werden.

Ein grüner CI-Lauf ist kein Ersatz für die Betreiberabnahme. Tests mit simulierten LDAP-/SMTP-Servern weisen keine Erreichbarkeit oder korrekte Konfiguration des realen Air-Gap-Verzeichnisses nach.

## 2. Abnahmematrix

| ID | Sicherheitsziel / Anforderung | Prüfverfahren und erwartetes Ergebnis | Nachweis / Ablage | Status |
|---|---|---|---|---|
| IAM-01 | Nicht angemeldete Benutzer erhalten keinen Zugriff auf geschützte API-Funktionen. | Ohne Sitzung Projekt- und Review-API aufrufen. Erwartung: HTTP 401; keine Daten werden ausgeliefert. | Automatisiert: `backend/tests/test_auth.py`; CI Backend Linux. | Test vorhanden |
| IAM-02 | Rollen werden serverseitig durchgesetzt. | Operator, Reviewer, Approver, Admin und kombinierte Rollen getrennt anmelden; erlaubte und verbotene Aktionen prüfen. Erwartung: unzulässige Aktionen HTTP 403. | Automatisiert: `test_auth.py`, Rollen- und Routenmatrix. | Test vorhanden |
| IAM-03 | Alle API-Routen sind rollenbezogen vollständig geprüft. | Für jede registrierte API-Route und HTTP-Methode muss genau eine Rollen-Policy existieren; erlaubte und verweigerte Rollen werden automatisiert geprüft. Unbekannte Routen werden standardmäßig verweigert. | `backend/tests/test_auth.py`: `test_api_route_role_matrix_covers_every_registered_route`, `test_unclassified_api_routes_are_denied_by_default`; [vollständige Route-/Rollenmatrix](API-AUTORISIERUNGSMATRIX.md). | Test vorhanden |
| IAM-04 | CSRF-Schutz für zustandsändernde Aktionen. | Zustandsändernde Anfrage ohne bzw. mit falschem CSRF-Token senden. Erwartung: Ablehnung; gültiger Token ermöglicht Aktion. | Automatisiert: `backend/tests/test_auth.py`. | Test vorhanden |
| IAM-05 | Passwortspeicherung und Sitzungen sind angemessen geschützt. | Datenbank auf Klartextpasswörter prüfen; Session-Hash, Ablauf und Logout testen. Erwartung: Passwort nicht im Klartext, abgelaufene/abgemeldete Sitzung ungültig. | Automatisiert: `backend/tests/test_auth.py`. | Test vorhanden |
| IAM-06 | Brute-Force-Anmeldeversuche werden begrenzt. | Mehrere falsche Passwörter in definiertem Zeitfenster senden. Erwartung: nach Grenzwert HTTP 429; keine vertraulichen Details in Antwort. | Automatisiert: `backend/tests/test_auth.py`. | Test vorhanden |
| IAM-07 | LDAP-Konten erhalten ausschließlich explizit konfigurierte Rollen. | LDAP-Gruppenmitgliedschaft, fehlende Gruppe, unbekannte Gruppe und gleichnamiges lokales Konto testen. Erwartung: nur erlaubte Gruppen werden zugeordnet; kein lokaler Fallback bei LDAP. | Automatisiert: `backend/tests/test_ldap_auth.py`, `test_deployment.py`; zusätzlich reale AD-Abnahme. | Teilweise |
| IAM-08 | LDAP-Verbindung ist verschlüsselt und Zertifikate werden geprüft. | LDAPS und StartTLS mit gültigem, ungültigem und nicht vertrauenswürdigem Zertifikat testen. Erwartung: nur gültige TLS-Verbindung wird akzeptiert. | Automatisierte Konfigurations-/Mocktests vorhanden; realer Zertifikatstest im Air-Gap-Netz erforderlich. | Teilweise |
| IAM-09 | Deaktivierte Benutzer bzw. geänderte Rollen verlieren unzulässigen Zugriff. | Benutzer deaktivieren bzw. Rollen ändern, bestehende Sitzungen und Folgeanfragen prüfen. Erwartung: deaktivierte Sitzungen werden widerrufen; Rollenänderungen wirken sofort. | Automatisiert: `test_auth.py`: `test_admin_can_update_roles_and_disable_user_and_sessions_are_revoked`, `test_role_changes_take_effect_for_existing_sessions_immediately`. | Test vorhanden |
| DEP-01 | Standalone ist ausschließlich lokal erreichbar. | Konfiguration mit Loopback starten; von anderem Gerät im LAN verbinden. Erwartung: kein Netzwerkzugriff möglich. | Automatisiert: `backend/tests/test_deployment.py`; Paket-Smoke-Test; zusätzlicher Test auf Zielsystem. | Teilweise |
| DEP-02 | Netzwerkprofil verlangt explizite Bind-Adresse und TLS. | Netzwerkprofil ohne Bind-Adresse, Zertifikat oder Schlüssel starten. Erwartung: Start wird abgelehnt. Mit gültiger Konfiguration HTTPS-Verbindung herstellen. | Automatisiert: `backend/tests/test_deployment.py`, `packaging/network_smoke_test.py`; reale Firewall-/Zertifikatsabnahme. | Teilweise |
| DEP-03 | Anwendung benötigt zur Laufzeit keinen Internetzugriff. | Zielsystem vom Internet trennen; Start, Anmeldung, Regelverwaltung, Verarbeitung, Review und Export ausführen; ausgehende Verbindungen überwachen. Erwartung: Kernfunktionen vollständig offline. | Betreiberprotokoll mit Betriebssystem, Paketversion, Netzwerkbeobachtung und Testergebnis. | Offen |
| CFG-01 | Geheimnisse dürfen nicht in JSON-Konfiguration oder Repository liegen. | Deployment-Konfiguration mit Schlüsselbegriffen wie password/secret/token prüfen; Repository und Paket auf echte Geheimnisse scannen. Erwartung: Konfigurationsprüfung lehnt Geheimnisse ab; keine echten Zugangsdaten committed. | Automatisiert: `backend/tests/test_deployment.py`; zusätzlich Secret-Scan vor Release. | Teilweise |
| CFG-02 | TLS-Privatschlüssel und Datenverzeichnis sind für Unbefugte nicht verfügbar. | Dateirechte auf Zielsystemen prüfen; Windows- und Linux-Benutzerkonten testen. Erwartung: Zugriff nur für erforderliche Benutzer/Admins. | Betreiberprotokoll; OS-spezifische Prüfung. | Offen |
| DATA-01 | Originaldateien bleiben unverändert. | Vorher-/Nachher-Hash der Quelldatei vergleichen; auch bei Fehler, Abbruch und ungültiger Eingabe prüfen. Erwartung: Quellhash bleibt identisch. | Automatisiert: `backend/tests/test_sanitizer.py`; ergänzende Zielsystem-Stichprobe. | Test vorhanden |
| DATA-02 | Fehlerhafte oder abgebrochene Verarbeitung erzeugt keine freigabefähige Teilausgabe. | Ungültiges Encoding, fehlerhaftes JSONL und Abbruch simulieren. Erwartung: Lauf nicht erfolgreich/freigegeben; Teiloutput wird entfernt oder eindeutig verworfen. | Automatisiert: `backend/tests/test_sanitizer.py`, `test_review_workflow.py`. | Teilweise |
| DATA-03 | Große Dateien werden speicherschonend verarbeitet. | 64-MiB-Regeltest mit Tracemalloc und 5-GiB-End-to-End-Lauf ausführen. Erwartung: kein vollständiges Einlesen in den RAM; dokumentierte Laufzeit und Peak-RSS. | `backend/tests/test_streaming_performance.py`; `packaging/benchmark_sanitizer.py`; CI-Meilensteinbericht. | Test vorhanden |
| DATA-04 | Regelprüfung erkennt alle relevanten sensiblen Inhalte der freigegebenen Logquellen. | Pro Quellprofil repräsentativen Testkorpus mit Positiv- und Negativfällen, Unicode, Mehrzeilern, Escaping und Grenzfällen verwenden. Erwartung: fachlich definierte Erkennungsquote und dokumentierte False-Negatives. | Fachlicher Testkatalog und Freigabe durch Daten-/Regelverantwortliche. | Offen |
| DATA-05 | Mapping-Daten sind konsistent und vor unberechtigtem Zugriff geschützt. | Gleiche Werte über Dateien und Läufe prüfen; Datenverzeichnis-Zugriff mit OS-Benutzerrollen testen. Erwartung: konsistente Platzhalter; nur berechtigte lokale Konten erhalten Dateizugriff. | `backend/tests/test_mapping_store.py`; Betreiberprüfung. Mapping-SQLite ist nicht zusätzlich verschlüsselt. | Teilweise |
| REV-01 | Freigabe erfordert bestandene Pflichtprüfungen und ggf. menschliche Reviewer-Entscheidung. | Lauf mit zugewiesenem Reviewer, ohne Reviewer, mit fehlgeschlagener Validierung und mit Rückgabe testen. Erwartung: Zustandsübergänge folgen der Rollen- und Freigabelogik. | Automatisiert: `backend/tests/test_review_workflow.py`; Ende-zu-Ende-Protokoll. | Teilweise |
| REV-02 | Zurückgewiesene, gestoppte und fehlgeschlagene Läufe sind nicht exportierbar. | Für jeden negativen Status Exportversuch durchführen. Erwartung: Server verweigert Export; keine Datei/ZIP wird ausgeliefert. | `backend/tests/test_review_workflow.py`; gezielte Negativtests für jeden Status erforderlich. | Teilweise |
| REV-03 | Manipulierte Ausgabe nach Prüfung/Freigabe wird erkannt. | Interne Ausgabedatei nach Validierung bzw. Review verändern und anschließend Suche/Freigabe/Export versuchen. Erwartung: Integritätsabweichung führt zur Ablehnung. | Automatisiert: Review-Workflow-Test enthält Manipulationsprüfung; Exportpfad zusätzlich abnehmen. | Teilweise |
| REV-04 | Prüferentscheidungen und Exporte sind nachvollziehbar. | Freigabe, Rückgabe, Kommentar, Stop und Export ausführen; Auditdatensätze mit Benutzer/Zeitpunkt/Aktion/Bezug prüfen. Erwartung: vollständige, konsistente Historie ohne Loginhalte. | `backend/tests/test_review_workflow.py`; Audit-Stichprobe im Abnahmeprotokoll. | Teilweise |
| REV-05 | Export enthält ausschließlich freigegebene Dateien und überschreibt keine vorhandenen Zieldateien. | Gemischtes Projekt mit freigegebenen, zurückgewiesenen und fehlgeschlagenen Ergebnissen exportieren; vorhandenes Ziel testen. Erwartung: nur freigegebene Ausgaben, keine Überschreibung. | Automatisierte Export-Negativtests ergänzen; Windows-/Linux-Browserprüfung. | Offen |
| LOG-01 | Audit und Diagnose enthalten keine sensiblen Loginhalte, Tokens oder Mappings. | Testdaten mit eindeutigen Canary-Secrets verarbeiten; Logs, Fehlerantworten, Audit und E-Mail nach Canary-Werten durchsuchen. Erwartung: keine Canary-Werte in Metadaten/Diagnose. | SMTP-Tests: `backend/tests/test_notifications.py`; zusätzlicher Log-/Audit-Canary-Test. | Teilweise |
| LOG-02 | SMTP-Benachrichtigungen sind verschlüsselt und enthalten keine Loginhalte. | STARTTLS/SSL, Empfänger, SMTP-Ausfall und Nachrichteninhalt prüfen. Erwartung: sichere Transportoption; keine Originalpfade, Kommentare oder Logauszüge im Mailtext. | Automatisiert: `backend/tests/test_notifications.py`; echter SMTP-Abnahmetest im Air-Gap-Netz. | Teilweise |
| BAK-01 | Datenbestand kann vollständig gesichert und wiederhergestellt werden. | Datenbank, Projekte, Mapping, Regeln, Review- und Auditdaten sichern; auf frischer Installation wiederherstellen. Erwartung: Projekte und Statushistorie konsistent, Anwendung startet. | Dokumentierter Backup-/Restore-Test mit Datum, Version, Prüfsummen und Ergebnis. | Offen |
| SUP-01 | Portable Artefakte stammen aus nachvollziehbarem Build. | Windows-/Linux-Build, Smoke-Test, Commit-SHA und Artefakt-Prüfsumme dokumentieren. Erwartung: beide Pakete starten auf Zielplattformen und passen zum freigegebenen Commit. | GitHub Actions: `.github/workflows/milestone-validation.yml`; Release-Workflow; manuelle Zielsystemprüfung. | Teilweise |
| SUP-02 | Abhängigkeiten und Quellcode werden vor Release auf bekannte Schwachstellen geprüft. | Dependency-/Secret-Scanning und Review von Sicherheitsmeldungen ausführen. Erwartung: keine ungeklärten kritischen Findings; Ausnahmen mit Risikoakzeptanz. | CI-/Release-Bericht, Scan-Artefakte und Freigabeprotokoll. | Offen |
| OPS-01 | Sicherheitsvorfälle können erkannt und behandelt werden. | Tabletop-Übung zu Datenabfluss, kompromittiertem Benutzer, kompromittierter Regel und versehentlichem Export. Erwartung: Verantwortliche, Stop-/Isolationsmaßnahmen und Kommunikationsweg bekannt. | Übungsprotokoll und Incident-Kontaktliste. | Offen |
| OPS-02 | Aufbewahrung und sichere Löschung sind geregelt. | Datenlebenszyklus für Originale, Arbeitsdateien, Exporte, Backups und temporäre Dateien festlegen und stichprobenartig prüfen. Erwartung: definierte Fristen und dokumentierte Löschverantwortung. | Betreiber-Richtlinie und Löschprotokoll. | Offen |

## 2.1 API-Autorisierung (IAM-03)

Die vollständige HTTP-Methoden-/Rollenmatrix ist in [LS-SEC-003 – API-Autorisierungsmatrix](API-AUTORISIERUNGSMATRIX.md) dokumentiert. Die Implementierung enthält 46 explizite Method-/Routen-Policies. Ein automatisierter Test gleicht sämtliche registrierten API-Routen mit der Policy-Tabelle ab; fehlende oder doppelte Zuordnungen lassen den Test fehlschlagen. Nicht klassifizierte API-Routen werden standardmäßig verweigert (fail closed).

Die Rollen sind funktionsbezogen getrennt: Operatoren bearbeiten Projekte und dürfen Laufhistorie sowie freigegebene Exporte lesen; Reviewer und Approver bearbeiten den Prüfprozess; Rule Owner verwalten Regeln; Administratoren verwalten Benutzer und besitzen die explizit zugewiesenen Administrationsrechte. Mehrfachrollen vereinigen die jeweiligen Berechtigungen.

**Abgrenzung:** Es gibt keine projektbezogene Mandanten- oder Eigentümertrennung. Operatoren arbeiten projektübergreifend; Reviewer und Approver sehen den gemeinsamen Prüfbestand. Diese Eigenschaft ist bei der Betreiberbewertung zu berücksichtigen.

## 3. Verbindliche Testläufe

### 3.1 Pull-Request- und Push-CI

Workflow: `.github/workflows/ci.yml`

Erwarteter Umfang laut CI-Definition:

- Backend-Pytest-Suite auf Ubuntu.
- Backend-Regressionsauswahl auf Windows.
- Ruff-Linting auf Linux und Windows.
- Frontend-Tests und Produktionsbuild.

Ausführung lokal (Backend):

```bash
cd backend
python -m pip install -e ".[dev]"
pytest
ruff check src tests
```

Ausführung lokal (Frontend):

```bash
cd frontend
npm install
npm test
npm run build
```

**Abnahmeregel:** Alle für den Commit erforderlichen Checks müssen erfolgreich sein. Windows führt aktuell nicht die vollständige Backend-Suite aus; dies ist bei der Bewertung der Plattformabdeckung zu berücksichtigen.

### 3.2 Meilensteinprüfung / portable Pakete

Workflow: `.github/workflows/milestone-validation.yml`

- Portable PyInstaller-Pakete für Windows und Linux.
- Standalone-Smoke-Test für beide Plattformen.
- HTTPS-Netzwerk-Smoke-Test für beide Plattformen.
- Synthetischer 5-GiB-Benchmark auf Linux.

**Abnahmeregel:** Alle drei Jobs müssen erfolgreich sein. Artefakte, Run-ID, Commit-SHA und Prüfsummen sind im Abnahmeprotokoll zu erfassen. Der synthetische Benchmark ersetzt keine Messung mit repräsentativen Logs auf der tatsächlichen Zielhardware.

### 3.3 Zielsystem-Abnahme

Die folgenden Prüfungen sind zwingend auf den vorgesehenen Geräten auszuführen:

1. Windows- und Linux-Paket jeweils frisch entpacken und starten.
2. Standalone-Zugriff von einem zweiten Gerät aus nachweislich ausschließen.
3. Offlinebetrieb ohne Internetverbindung für den vollständigen Arbeitsablauf testen.
4. Repräsentative Logs aus jeder freigegebenen Quelle verwenden.
5. Originaldatei-Hash vor und nach der Verarbeitung vergleichen.
6. Zurückweisung, Stop, Freigabe und Export einschließlich Negativfällen testen.
7. 5-GiB- oder repräsentative Großdatei messen: Laufzeit, CPU, Peak-RAM, temporärer Speicher und Ergebnisintegrität.
8. Datenverzeichnis sichern und auf einer Testinstallation wiederherstellen.
9. Bei Netzwerkbetrieb LDAP/AD mit allen benötigten Rollen, ungültigen Zertifikaten, fehlenden Gruppen und SMTP-Ausfall testen.
10. Firewall-Regeln und TLS-Zertifikatskette durch den Netzwerkverantwortlichen bestätigen lassen.

## 4. Abnahmeprotokoll (auszufüllen)

| Feld | Eintrag |
|---|---|
| Organisation / Betreiber | [eintragen] |
| System / Inventar-ID | [eintragen] |
| Betriebsart | [Standalone / Air-Gap] |
| Betriebssystem / Version | [eintragen] |
| LogSanitizer-Version / Commit-SHA | [eintragen] |
| CI-Run-ID / Link | [eintragen] |
| Paket-Prüfsumme (SHA-256) | [eintragen] |
| Testdatum | [eintragen] |
| Tester / Rolle | [eintragen] |
| Offene Findings | [eintragen] |
| Akzeptierte Restrisiken / Genehmiger | [eintragen] |
| Entscheidung | [freigegeben / bedingt freigegeben / abgelehnt] |
| Unterschrift / Freigabedatum | [eintragen] |

## 5. Freigaberegeln

Eine Produktivfreigabe ist erst zulässig, wenn:

- alle als kritisch eingestuften Prüfungen bestanden oder mit dokumentierter Risikoakzeptanz behandelt wurden;
- IAM-03 (vollständige API-Autorisierungsmatrix), DATA-04 (fachliche Erkennungsqualität), REV-02/REV-05 (Export-Negativfälle) und BAK-01 (Wiederherstellung) nachgewiesen sind;
- die Zielsystem-Abnahme für die konkrete Betriebsart vorliegt;
- offene Findings einen Verantwortlichen, Termin und eine Entscheidung besitzen;
- der Betreiber die Restrisiken aus LS-SEC-001 ausdrücklich akzeptiert hat.

## 6. Pflege

Die Matrix ist bei Änderungen an Authentifizierung, Rollen, API, Sanitizer, Review, Export, Datenhaltung, Deployment oder Paketierung zu aktualisieren. Mindestens jährlich ist eine erneute Betreiberprüfung durchzuführen.

## 7. Referenzen

- [Sicherheitskonzept LS-SEC-001](SICHERHEITSKONZEPT.md)
- [Anforderungen v2.8](../REQUIREMENTS.md)
- [Architektur](../ARCHITECTURE.md)
- [Deployment](../DEPLOYMENT.md)
- [CI-Strategie](../CI.md)
- [Sicherheitsbewertung](../SECURITY_REVIEW.md)
