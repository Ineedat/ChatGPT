# API-Autorisierungsmatrix – LogSanitizer

**Dokument-ID:** LS-SEC-003  
**Version:** 1.0  
**Stand:** 05.11.2026  
**Bezug:** LS-SEC-001 Sicherheitskonzept, LS-SEC-002 technische Abnahmematrix, Anforderungen v2.8  
**Implementierungsstand:** Commit `af433f1120714821430672986c1fba1cb5dca7cb` (CI erfolgreich)

## 1. Zweck und Geltungsbereich

Dieses Dokument beschreibt die serverseitige Autorisierung der registrierten HTTP-API-Routen. Die Berechtigungsprüfung erfolgt im Backend und ist unabhängig davon, ob die Oberfläche Funktionen ein- oder ausblendet.

Die Tabelle wird aus der zentralen Policy-Definition in `backend/src/logsanitizer/auth.py` abgeleitet. Der automatisierte Test `test_api_route_role_matrix_covers_every_registered_route` vergleicht alle registrierten API-Routen und HTTP-Methoden mit dieser Definition. Jede Route muss genau eine passende Policy besitzen. Nicht zugeordnete API-Routen werden verweigert (fail closed).

## 2. Rollen

| Kürzel | Rolle | Aufgabenbereich |
|---|---|---|
| admin | Administrator | Benutzer- und Rollenverwaltung sowie vollständiger Anwendungszugriff |
| operator | Bearbeiter | Projekte, Dateiimport, Regelanwendung, Laufhistorie, Vergleich und Export freigegebener Ergebnisse |
| reviewer | Prüfer | Prüfwarteraum, Suche, Kommentare, Rückgabe, Stopp, Freigabe und Prüf-Audit |
| approver | Freigeber | Prüffunktionen und formale Freigabe |
| rule_owner | Regelverantwortlicher | Regelbibliothek, Regelkonfiguration, Regelvorschau und Dateivorschau |

Mehrfachrollen werden vereinigt. Eine Person kann daher mehrere Aufgaben übernehmen, ohne dass eine Rolle die Rechte einer anderen aufhebt.

## 3. Vollständige Route-/Methodenmatrix

Die Spalte „Erlaubte Rollen“ benennt ausschließlich die Rollen, die die jeweilige Route erreichen dürfen. Alle nicht aufgeführten Rollen erhalten HTTP 403. Nicht angemeldete Benutzer erhalten bei geschützten Routen HTTP 401.

| Methode | API-Route | Erlaubte Rollen |
|---|---|---|
| `GET` | `/api/docs` | admin, operator, reviewer, approver, rule_owner |
| `GET` | `/api/docs/oauth2-redirect` | admin, operator, reviewer, approver, rule_owner |
| `GET` | `/api/openapi.json` | admin, operator, reviewer, approver, rule_owner |
| `POST` | `/api/auth/login` | admin, operator, reviewer, approver, rule_owner |
| `GET` | `/api/auth/me` | admin, operator, reviewer, approver, rule_owner |
| `POST` | `/api/auth/logout` | admin, operator, reviewer, approver, rule_owner |
| `GET` | `/api/auth/users` | admin |
| `POST` | `/api/auth/users` | admin |
| `PUT` | `/api/auth/users/{user_id}` | admin |
| `DELETE` | `/api/auth/users/{user_id}` | admin |
| `GET` | `/api/projects` | admin, operator |
| `POST` | `/api/projects` | admin, operator |
| `GET` | `/api/projects/{project_id}` | admin, operator |
| `GET` | `/api/projects/{project_id}/files` | admin, operator |
| `POST` | `/api/projects/{project_id}/files` | admin, operator |
| `POST` | `/api/projects/{project_id}/files/{file_id}/detect-format` | admin, operator |
| `PUT` | `/api/projects/{project_id}/files/{file_id}/format` | admin, operator |
| `POST` | `/api/projects/{project_id}/files/{file_id}/validate-format` | admin, operator |
| `POST` | `/api/projects/{project_id}/files/{file_id}/preview` | admin, operator, rule_owner |
| `POST` | `/api/projects/{project_id}/files/{file_id}/sanitize-jobs` | admin, operator |
| `GET` | `/api/projects/{project_id}/files/{file_id}/sanitize-jobs/{job_id}` | admin, operator |
| `POST` | `/api/projects/{project_id}/files/{file_id}/sanitize-jobs/{job_id}/cancel` | admin, operator |
| `POST` | `/api/projects/{project_id}/files/{file_id}/sanitize` | admin, operator |
| `POST` | `/api/projects/{project_id}/files/import-folder` | admin, operator |
| `POST` | `/api/projects/{project_id}/files/upload` | admin, operator |
| `GET` | `/api/rules/library` | admin, rule_owner |
| `POST` | `/api/rules/preview` | admin, rule_owner |
| `GET` | `/api/rules/config` | admin, rule_owner |
| `POST` | `/api/rules/config/validate` | admin, rule_owner |
| `PUT` | `/api/rules/config` | admin, rule_owner |
| `GET` | `/api/reviews/runs/{run_id}/compare-preview` | admin, operator, reviewer, approver |
| `GET` | `/api/reviews/queue` | admin, reviewer, approver |
| `GET` | `/api/reviews/runs` | admin, operator, reviewer, approver |
| `GET` | `/api/reviews/runs/{run_id}/search` | admin, reviewer, approver |
| `GET` | `/api/reviews/saved-searches` | admin, reviewer, approver |
| `POST` | `/api/reviews/saved-searches` | admin, reviewer, approver |
| `DELETE` | `/api/reviews/saved-searches/{search_id}` | admin, reviewer, approver |
| `POST` | `/api/reviews/runs/{run_id}/approve` | admin, reviewer, approver |
| `POST` | `/api/reviews/runs/{run_id}/return` | admin, reviewer, approver |
| `POST` | `/api/reviews/runs/{run_id}/stop` | admin, reviewer, approver |
| `POST` | `/api/reviews/runs/{run_id}/comments` | admin, reviewer, approver |
| `GET` | `/api/reviews/projects/{project_id}/exports/approved` | admin, operator, reviewer, approver |
| `GET` | `/api/reviews/projects/{project_id}/exports/approved/{run_id}/content` | admin, operator, reviewer, approver |
| `GET` | `/api/reviews/projects/{project_id}/exports/approved.zip` | admin, operator, reviewer, approver |
| `GET` | `/api/reviews/exports/audit` | admin, operator, reviewer, approver |
| `GET` | `/api/reviews/audit` | admin, reviewer, approver |

### Öffentliche bzw. allgemeine Ausnahmen

- `GET /api/health`: öffentlich, liefert ausschließlich einen minimalen Liveness-Status.
- `POST /api/auth/login`: öffentlich, Zugangsdaten werden serverseitig geprüft und Anmeldeversuche begrenzt.
- `GET /api/docs`, `GET /api/docs/oauth2-redirect` und `GET /api/openapi.json`: nur mit gültiger Sitzung erreichbar; keine anonyme API-Dokumentation.
- `GET /api/auth/me` und `POST /api/auth/logout`: für alle angemeldeten Rollen; Logout zusätzlich CSRF-geschützt.

## 4. Wichtige Abgrenzungen

1. **Operator und Review:** Operatoren dürfen die Laufhistorie lesen und freigegebene Ergebnisse vergleichen bzw. exportieren. Sie dürfen keine Prüferwarteschlange, Prüferentscheidungen, Kommentare oder Prüf-Auditdaten verwalten.
2. **Reviewer und Approver:** Beide Rollen dürfen den Review-Workflow verwenden. Projektanlage, Dateiimport und Sanitizer-Ausführung bleiben ihnen verwehrt.
3. **Regelverantwortliche:** Sie dürfen Regeln verwalten und eine Dateivorschau aufrufen, erhalten aber keine allgemeine Projekt- oder Sanitizer-Berechtigung.
4. **Benutzerverwaltung:** Benutzer und Rollen können ausschließlich Administratoren verwalten.
5. **Unbekannte Routen:** Neue API-Routen sind vor ihrer Nutzung explizit in die Policy-Tabelle aufzunehmen. Ohne Eintrag erfolgt eine Verweigerung – auch für Administratoren.
6. **Keine Projekt-Mandantentrennung:** Die Rollen begrenzen Funktionsbereiche, nicht einzelne Projekte oder Benutzer-Datensätze. Operatoren arbeiten innerhalb ihrer Rolle projektübergreifend; Reviewer/Approver sehen den gemeinsamen Prüfbestand. Eine projektbezogene Eigentümer- oder Mandantentrennung ist derzeit nicht implementiert und darf nicht als Sicherheitsmerkmal angenommen werden.

## 5. Automatisierte Nachweise

| Prüfung | Zweck |
|---|---|
| `test_api_route_role_matrix_covers_every_registered_route` | Jede registrierte API-Route und Methode muss genau einer Rollen-Policy zugeordnet sein; Rollen werden gegen die Policy geprüft. |
| `test_unclassified_api_routes_are_denied_by_default` | Unbekannte API-Routen werden auch für Administratoren verweigert. |
| `test_role_matrix_keeps_operator_and_review_permissions_separate` | Integrationstest für Operator, Reviewer, Approver, Admin und kombinierte Rollen. |
| `test_rule_owner_can_manage_rules_but_cannot_process_or_manage_projects` | Regelverantwortliche dürfen Regeln bearbeiten, aber keine Projekte verwalten oder verarbeiten. |
| `test_role_changes_take_effect_for_existing_sessions_immediately` | Rollenänderungen gelten für bestehende Sitzungen sofort. |
| `test_admin_can_update_roles_and_disable_user_and_sessions_are_revoked` | Deaktivierung entzieht bestehende Sitzungen. |

### CI-Nachweis

CI-Lauf: [GitHub Actions – 41965230514](https://github.com/Ineedat/ChatGPT/actions/runs/41965230514)

Ergebnis: Backend Ubuntu erfolgreich, Backend Windows-Regressionsauswahl erfolgreich, Ruff Linux/Windows erfolgreich, Frontend-Tests und Build erfolgreich.

Die Windows-Pipeline führt weiterhin nicht die vollständige Backend-Suite aus. Die vollständige Backend-Suite ist in diesem CI-Lauf auf Ubuntu ausgeführt worden.

## 6. Verbleibende Betreiberprüfungen

Die automatisierte Matrix ersetzt nicht die Abnahme auf den Zielsystemen. Für die Produktivsetzung sind insbesondere reale LDAP-Gruppenzuordnungen, deaktivierte AD-Konten, TLS-Zertifikate, Netzwerkprofil, Firewall und die tatsächliche Benutzerzuweisung zu prüfen.

