# Architekturentscheidungen

```text
React/TypeScript UI -> FastAPI (loopback standardmäßig)
                         |-- Projekt-/Importdienste
                         |-- Format-Erkennung (geplant)
                         |-- Regel-Engine + Streaming (geplant)
                         |-- Validierung/Freigabestatus (geplant)
                         |-- Rollen/Review/Audit (geplant)
                         |-- SQLite-Metadaten
                         |-- separat geschützte Mapping-Daten
                         |-- getrennte temporäre Daten und Ausgaben
```

## Leitlinien
1. Lokal-first; keine Laufzeitabhängigkeit vom Internet.
2. Sicherer Standard: nur 127.0.0.1; keine Netzwerkfreigabe ohne Authentifizierung und Autorisierung.
3. Streaming mit begrenzten Puffern, keine vollständigen 5-GB-Dateien im RAM.
4. Quelldateien sind schreibgeschützte Eingaben.
5. Import, Verarbeitung, Validierung, wartende Prüfung, Rückgabe, Freigabe und Export sind getrennte Zustände.
6. Fail-closed: unvollständige Läufe und Pflichtprüfungsfehler sind nicht freigabefähig.
7. Regeln, Mappings, Zugangsdaten, Diagnose und Auditdaten haben getrennte Schutz-/Offenlegungsregeln.
8. Neue Läufe verweisen auf vorherige Läufe; Audit kopiert keine Loginhalte.
9. GUI-Hilfe ist lokal eingebunden und zugänglich.
10. Validierung reduziert Risiken, garantiert aber nicht die Erkennung jedes sensiblen Werts.
11. Import registriert zunächst nur lokale Quelldateipfade und Metadaten; Quelldateiinhalte werden nicht in SQLite kopiert.

## Initialer API-Vertrag
- GET /api/health: minimaler Liveness-Status ohne lokale Daten offenzulegen.
- GET /api/projects/{project_id}/files: registrierte Quelldatei-Metadaten.
- POST /api/projects/{project_id}/files: absolute lokale Quelldatei registrieren, ohne Inhalte zu lesen.
- POST /api/projects/{project_id}/files/import-folder: Dateien eines absoluten lokalen Ordners registrieren, rekursiv optional, mit per-Datei-Fehlerliste und Limit von 5.000 Kandidaten.

## Während der Implementierung zu entscheiden
- Verschlüsselung und Schlüsselverwaltung für persistente Mappings.
- Unterstützte Encodings und Umgang mit fehlerhaften Bytes.
- Grenzen für Regex-Ausführung.
- Umgang mit sehr großen einzelnen JSON-Dokumenten.
- Cross-platform-Paketierung und abgesicherter Netzwerkmodus.
- Sicherer lokaler Dateiauswahldialog für große Dateien und Ordner auf Windows/Linux.
