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
- [ ] Einzeldatei-/Ordnerimport, Originale bleiben unverändert.
- [ ] Format-Erkennung mit explizitem Umgang mit unbekannten Formaten.
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
