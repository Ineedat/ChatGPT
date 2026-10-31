# Architekturentscheidungen

**Gültige Anforderungsbaseline:** v2.8. Performance, Bedienbarkeit und Wartbarkeit haben Vorrang. Zielbetrieb ist ausschließlich Standalone-Laptop oder ein definiertes Air-Gap-Netz.

```text
React/TypeScript UI -> FastAPI
                         |-- Projekt-/Importdienste
                         |-- Format-Erkennung und Validierung
                         |-- Regel-Engine + Streaming
                         |-- Rollen / Review / Audit
                         |-- SQLite-Metadaten und lokale Mapping-Daten
                         |-- temporäre Daten und frei wählbare Ausgaben
```

## Leitlinien

1. Lokal-first; keine Laufzeitabhängigkeit vom Internet.
2. Standalone standardmäßig nur auf 127.0.0.1. Netzwerkbetrieb nur nach ausdrücklicher Konfiguration für das definierte Air-Gap-Netz.
3. Streaming mit begrenzten Puffern; große Dateien dürfen nicht vollständig in den RAM geladen werden.
4. Quelldateien sind schreibgeschützte Eingaben.
5. Import, Verarbeitung, Validierung, wartende Prüfung, Rückgabe, Freigabe und Export sind getrennte Zustände.
6. Fehlgeschlagene oder unvollständige Läufe dürfen nicht als erfolgreich/freigegeben gelten.
7. Benutzerrollen bleiben verbindlich: Administrator, Rule Owner, Processor und Reviewer/Releaser. Eine Person kann mehrere Rollen übernehmen.
8. Mapping-Daten werden einfach lokal in SQLite gehalten. Verschlüsselung mit separater Schlüsseldatei und komplexe Schlüsselverwaltung sind keine Anforderungen.
9. Ausgabepfade sind flexibel wählbar; ein verpflichtender Workspace mit Pfad-Allowlist oder OS-spezifische Race-Härtung ist nicht erforderlich.
10. UI-Hilfe ist lokal eingebunden und zugänglich.
11. Validierung reduziert Risiken, garantiert aber nicht die Erkennung jedes sensiblen Werts.

## Initialer API-Vertrag

- GET /api/health: minimaler Liveness-Status.
- GET /api/projects/{project_id}/files: registrierte Quelldatei-Metadaten.
- POST /api/projects/{project_id}/files: lokale Quelldatei registrieren, ohne sie zu verändern.
- POST /api/projects/{project_id}/files/import-folder: Dateien eines lokalen Ordners registrieren, rekursiv optional.

## Performance- und UX-Entscheidungen

- Große Dateien werden streamend verarbeitet; RAM-Verbrauch und temporäre I/O sind zu messen.
- Unnötige Mehrfachdurchläufe und temporäre Indizes vermeiden.
- Fortschritt, Abbruch, verständliche Fehlermeldungen und klare Statusanzeigen haben Vorrang.
- Dateiauswahl, Ausgabepfad und Regelbearbeitung sollen möglichst wenige Bedienungsschritte erfordern.
- Automatische Format-Erkennung mit manueller Korrekturmöglichkeit.

## Rollen- und Prüfprozess

Erfolgreich validierte Läufe werden in der lokalen Laufhistorie protokolliert. Wenn ein Reviewer/Releaser zugewiesen ist, ist eine bewusste Freigabe erforderlich. Andernfalls erfolgt die automatische Freigabe nur nach bestandenen Pflichtprüfungen. Prüfer können bereinigte Ausgaben durchsuchen und Läufe freigeben, zurückgeben oder stoppen. Kommentare und begründete Ausnahmen bleiben nachvollziehbar protokolliert.

## Noch zu verifizieren

- Unterstützte Encodings und Umgang mit fehlerhaften Bytes.
- Grenzen für Regex-Ausführung und Ressourcenverbrauch.
- Umgang mit sehr großen einzelnen JSON-Dokumenten.
- Cross-platform-Paketierung und tatsächlicher Betrieb auf unterstützten Windows-/Linux-Versionen.
- Performance mit repräsentativen Dateien >= 5 GB.
- LDAP/AD- und SMTP-Integration im tatsächlichen Air-Gap-Zielnetz, sofern aktiviert.
