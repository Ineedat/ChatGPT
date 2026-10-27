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
- [ ] Versionierte Regelkonfiguration, Schema- und Konfliktprüfung.
- [ ] Streaming für Text und JSON, begrenzter Speicherbedarf.
- [ ] Stabile Projekt-Mappings, getrennt und geschützt gespeichert.
- [ ] Fortschritt, Abbruch, temporäre Datenbereinigung.
- [ ] Pflichtvalidierung und Scan nach Restmustern; Freigabe blockieren bei Fehlern.

## Meilenstein 2 — Prüfung und kontrollierte Freigabe
- [ ] Lokale Anmeldung und rollenbasierte Rechte.
- [ ] Prüfer-Warteschlange und sichere Suche.
- [ ] Freigabe/Rückgabe mit Kommentar, Laufhistorie und Audit.
- [ ] Begründete, eng begrenzte Ausnahmen.

## Meilenstein 3 — Deployment
- [ ] Optionale SMTP-Benachrichtigungen und Konfigurationstest.
- [ ] Optionale LDAP/AD-Integration.
- [ ] Geschützte Darksite-Netzwerkbindung.
- [ ] Portable Windows-/Linux-Paketierung und Offline-Handbuch.
- [ ] Sicherheits- und Performanceprüfung, Testdateien >= 5 GB.

## Definition of done
Eine Funktion benötigt Tests, verständliche Offline-Hilfe, sicheres Fehlerverhalten und Dokumentation. Sicherheitsfunktionen müssen auch abgewiesene/unzulässige Pfade testen.
