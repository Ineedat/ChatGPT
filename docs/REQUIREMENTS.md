# LogSanitizer — Anforderungen v2.8

Status: Neue fachliche Baseline (2026-10-29). Ersetzt Version 2.7.

## Produktziel und Betriebsgrenzen

LogSanitizer ist eine portable, lokal betriebene Anwendung zur schnellen und komfortablen Bereinigung großer Anwendungslogdateien. Sie wird ausschließlich in einer der folgenden Umgebungen eingesetzt:

- Standalone auf einem einzelnen Windows- oder Linux-Laptop, ohne Netzwerkfreigabe.
- In einem klar abgegrenzten, vom Internet getrennten Air-Gap-Netzwerk (Darksite).

Cloud-Dienste, externe APIs, CDN und Internetzugriffe zur Laufzeit sind ausgeschlossen. Ein allgemeiner Betrieb im Internet oder in nicht vertrauenswürdigen Netzen ist kein Produktziel.

**Prioritäten:** 1. Performance und geringer Ressourcenverbrauch, 2. einfache und intuitive Bedienung, 3. zuverlässige und nachvollziehbare Verarbeitung, 4. portable Installation und Wartbarkeit.

Das Projekt ist ausdrücklich keine Hochsicherheitsplattform. Zusätzliche Schutzmechanismen wie verpflichtende Verschlüsselung lokaler Mapping-Datenbanken, separate Schlüsselverwaltung, komplexe ACL-Vorgaben, ein fest vorgeschriebener Ausgabe-Workspace oder race-resistente OS-spezifische Dateiveröffentlichung sind keine Produktanforderungen. Die lokale Speicherung darf einfach und wartbar bleiben. Betriebssystem- und Dateisystem-Basisschutz sowie sichere Fehlerbehandlung bleiben sinnvoll, sollen aber die Bedienbarkeit und Performance nicht unnötig erschweren.

## Plattform und Betrieb

- Portable lokale Anwendung für Windows und Linux; macOS ist nicht vorgesehen.
- Vollständig offline, ohne Cloud, externe APIs, CDN oder Internetabhängigkeit im Betrieb.
- Standalone-Modus für einen Laptop sowie Netzwerkmodus ausschließlich für ein definiertes Air-Gap-Netz.
- Netzwerkzugriff nur nach ausdrücklicher Konfiguration der Bind-Adresse und mit Anmeldung/Rollenprüfung; keine Internet- oder öffentliche Netzwerkbereitstellung.
- Primär Anwendungslogs; einzelne Dateien und Ordner importieren, optional rekursiv. Import startet keine Verarbeitung.
- Quelldateien niemals automatisch ändern, verschieben oder löschen.
- Ausgabepfad und Arbeitsverzeichnis sollen für den Anwender verständlich und flexibel wählbar sein; keine verpflichtende zentrale Workspace-Allowlist.
- Portable Datenhaltung mit möglichst wenigen Dateien und einfacher Sicherung/Wiederherstellung.

## Stack und Skalierung

- Python/FastAPI, React/TypeScript, SQLite-Metadaten, versionierte JSON-Konfigurationen.
- Dateien von mindestens 5 GB streamend verarbeiten; gesamte Datei nicht in RAM laden.
- Speicher- und CPU-Verbrauch begrenzen; große Dateien sollen auch auf typischen Laptops praktikabel verarbeitet werden.
- Streaming statt unnötiger temporärer Indizes oder mehrfacher vollständiger Dateidurchläufe, sofern fachlich nicht erforderlich.
- Performance-Messungen und repräsentative große Testdateien sind verbindliche Abnahmekriterien.

## Regeln und Mappings

- Projekte können mehrere Logdateien und Quellenprofile enthalten; globale und profilspezifische Regeln.
- Format automatisch erkennen, manuelle Auswahl ermöglichen; unbekannte Formate nicht stillschweigend zuordnen.
- Strukturierte Erkennung (einschließlich JSON) und Text-/Regex-Regeln kombinieren; Multiline-Events und Stacktraces nach Möglichkeit erhalten.
- Regeln mit Name, aktiv/inaktiv, Literal oder Regex, Groß-/Kleinschreibung, Ersetzungsvorlage, Priorität und Profil.
- Regeln über GUI bearbeiten sowie versionierte JSON-Konfigurationen importieren/exportieren; Konflikte prüfen.
- Gleicher Originalwert muss innerhalb eines Projekts über Dateien und spätere Läufe konsistent ersetzt werden. Zuweisung unabhängig von Dateireihenfolge.
- Mapping-Daten dürfen einfach lokal gespeichert werden; verpflichtende Verschlüsselung, separate Schlüsseldatei, HMAC-Lookups und komplexe Schlüsselmigration sind nicht gefordert. Die Implementierung soll nachvollziehbar, performant und leicht wartbar sein.
- Allgemeine Regel-Exporte enthalten keine Mapping-Daten.
- Beispiel: [IP_1]; FQDN-Komponenten konfigurierbar, z. B. [Server_1].[Domain_1]. Doppelte Ersetzung vermeiden.

## Verarbeitung, Prüfung und Freigabe

- Regeltests, Vorschau, Fortschritt, Abbruch und klare Statusanzeigen.
- Unvollständige oder fehlgeschlagene Läufe dürfen nicht als erfolgreich angezeigt oder freigegeben werden.
- Pflichtprüfungen: technische/strukturelle Integrität und Suche nach verbliebenen sensiblen Mustern. Eine erfolgreiche Suche beweist nicht, dass alle sensiblen Daten erkannt wurden.
- Technische Validierung, menschliche Freigabe und Ausnahmen sind getrennte Zustände.
- Rollenmodell bleibt verbindlich: Administrator, Rule Owner, Processor, Reviewer/Releaser. Eine Person kann anfangs mehrere Rollen übernehmen.
- Wenn ein Prüfer zugewiesen ist, ist eine bewusste Freigabe durch einen autorisierten Prüfer erforderlich. Ohne Prüfer nur automatische Freigabe nach allen Pflichtprüfungen.
- Prüfersuche unterstützt Ad-hoc-Literal/Regex und gespeicherte Muster; Suchvorgänge dürfen die Verarbeitung nicht unkontrolliert ausbremsen.
- Rückgabe mit optionalem Kommentar sperrt regulären Export; erneute Verarbeitung erzeugt verknüpften Lauf.
- Ausnahmen nur mit Begründung; sie übergehen keine unabhängigen fehlgeschlagenen Pflichtprüfungen.

## Benutzer, Audit, Integration und Hilfe

- Lokale Benutzerkonten im Standalone-Modus.
- Im Air-Gap-Netzwerk optional LDAP/Active Directory; Rollen werden aus der konfigurierten Gruppenzuordnung abgeleitet. Keine unnötig komplexe Authentifizierungsarchitektur.
- Benutzerrollen und serverseitige Berechtigungsprüfungen bleiben erhalten.
- Audit protokolliert Benutzer, Zeitpunkt, Aktion, Entscheidung, Kommentar und Datei-/Lauf-/Regelbezüge, ohne Loginhalte zu kopieren.
- SMTP optional für Benachrichtigungen bei anstehender Prüfung und Rückgabe; SMTP-Ausfall darf die Verarbeitung nicht blockieren.
- Moderne, schlichte GUI mit möglichst wenigen Arbeitsschritten, verständlichen Bezeichnungen, sinnvollen Standardwerten und klaren Fehlermeldungen.
- MouseOver-Hilfe und tastaturzugängliche Erklärungen für GUI-Optionen.
- Ausführliche Hilfe vollständig offline, über Hilfemenü, F1 und kontextbezogene Hilfe.

## Nicht mehr geforderte Hochsicherheitsmaßnahmen

Die folgenden Punkte sind ausdrücklich keine Abnahmekriterien mehr und sollen bei der technischen Vereinfachung entfernt oder auf einfache Standardmechanismen zurückgeführt werden:

- AES-256-GCM-Verschlüsselung der lokalen Mapping-Datenbank und separate Schlüsseldatei.
- HMAC-basierte Mapping-Suche und aufwendige Schlüssel-/Datenbankmigration.
- Verpflichtende restriktive ACL-/Dateirechte-Verwaltung über die normalen Betriebssystemstandards hinaus.
- Zwingend vorgeschriebener Ausgabe-Workspace mit Pfad-Allowlist.
- OS-spezifische race-resistente Dateiveröffentlichung, Directory-Handle- und Reparse-Point-Sonderlogik.
- Hochsicherheitsbezogene Deployment-Komplexität, sofern sie für den Standalone- bzw. definierten Air-Gap-Betrieb keinen konkreten Nutzen bietet.

Nicht entfallen: Benutzerrollen, Anmeldung, Berechtigungsprüfungen, Prüferfreigabe, Audit-Historie, unveränderte Quelldateien, Fehlerbehandlung, Offline-Betrieb und Beschränkung des Netzwerkbetriebs auf das definierte Air-Gap-Netz.

## Kern-Abnahmekriterien

- Portable Windows-/Linux-Anwendung, vollständig offline lauffähig.
- Standalone-Betrieb auf einem Laptop und optionaler Betrieb in einem definierten Air-Gap-Netz.
- Mindestens 5-GB-Streaming mit dokumentiertem Speicher- und Laufzeitverhalten.
- Quelldateien bleiben unverändert; fehlgeschlagene/unvollständige Ausgabe wird nicht freigegeben.
- Konsistente projektweite Platzhalter und einfach bedienbare Regelverwaltung.
- Rollen, Prüferworkflow, Freigabe/Rückgabe und Audit bleiben funktionsfähig.
- Verständliche GUI, Offline-Hilfe und einfacher Installations-/Sicherungsprozess.

## Umsetzungsprinzip

Vorhandene Hochsicherheitsfunktionen werden nicht automatisch als dauerhaft erforderlich behandelt. Sie werden schrittweise vereinfacht oder entfernt, wenn dies die Wartbarkeit, Performance oder Bedienbarkeit verbessert. Änderungen müssen Tests, Dokumentation und Datenkompatibilität berücksichtigen. Die bestehende Projektfunktionalität und das Rollenmodell dürfen dabei nicht verloren gehen.
