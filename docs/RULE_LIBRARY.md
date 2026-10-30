# Vorkonfigurierte Regelbibliothek

Die integrierte Bibliothek enthält 20 editierbare Startvorlagen für typische Anwendungslogs. Sie ist über **Regeln → Vorlagenbibliothek** erreichbar und funktioniert vollständig offline.

## Enthaltene Kategorien

| Kategorie | Vorlagen |
|---|---|
| IP-Adresse | IPv4, IPv6-Heuristik |
| Hostname / Domain | FQDNs und Domains |
| Benutzername | Werte hinter `user=` und `username=` |
| E-Mail-Adresse | Übliche E-Mail-Syntax |
| Personenbezogene Daten | Telefonnummern-Heuristik, ISO- und deutsches Geburtsdatum |
| Passwort / Token / API-Key | `password=`, `passwd=`, `token=`, `api_key=`, `secret=`, HTTP-Bearer-Token |
| Dateipfad | Windows-Laufwerks-/UNC-Pfade, absolute Unix-Pfade |
| Systemname / Infrastruktur | Werte hinter `hostname=` und `server=`, MAC-Adressen |

## Vorlagen verwenden

1. Öffne **Regeln → Vorlagenbibliothek**.
2. Filtere optional nach Kategorie.
3. Prüfe Beschreibung, Regex-Muster, Beispiel und Hinweis.
4. Übernimm nur die Vorlagen, die zu den tatsächlich verwendeten Logquellen passen.
5. Die Vorlage erscheint im Regeleditor und ist zunächst **deaktiviert**.
6. Passe Suchmuster, Kategorie, Mapping-Präfix, Priorität und Quellprofil an.
7. Teste die Regel an synthetischen Beispielen. Aktiviere sie erst nach fachlicher Prüfung und speichere die Konfiguration.

Jede Übernahme erzeugt eine eigene Regelkopie. Sie kann unabhängig bearbeitet, deaktiviert oder gelöscht werden. Die Bibliothek selbst bleibt unverändert. Indexierte Ersetzungen verwenden projektweite Mappings, beispielsweise `[IP_1]` oder `[EMAIL_1]`.

## Wichtige Grenzen

- Die Bibliothek ist ein Startpunkt, kein vollständiger DLP-/Geheimnisscanner und keine Garantie, dass alle sensiblen Werte gefunden werden.
- Vorlagen werden bewusst deaktiviert eingefügt. Das verhindert, dass ungeprüfte Muster unbemerkt produktiv werden.
- Einige Muster sind heuristisch. Telefonnummern, Dateipfade und IPv6-Varianten können je nach Logformat Fehl- oder Nichttreffer erzeugen.
- Feldbezogene Geheimnisregeln erfassen nur die im Muster benannten Felder. Andere Schreibweisen wie `apiKey=`, `pwd=` oder proprietäre Header benötigen eigene Regelkopien.
- FQDN- und Hostnamenmuster können auch öffentliche Domains oder nicht vertrauliche Werte erfassen.
- Die technische Restmustersuche prüft nur konfigurierte Muster. Sie beweist nicht, dass alle personenbezogenen Daten oder Geheimnisse entfernt wurden.
- Ausschließlich synthetische Testwerte verwenden. Keine echten Passwörter, Tokens, API-Keys oder personenbezogenen Daten in Tests, Beispielen oder Screenshots hinterlegen.

## Erkennungsdetails

IPv4 verwendet eine Oktettbegrenzung von 0 bis 255. IPv6 ist eine Regex-Heuristik für verbreitete Schreibweisen; eingebettete IPv4-Endstücke und Zonen-IDs müssen bei Bedarf mit quellenspezifischen Regeln ergänzt werden. E-Mail-Adressen folgen einer üblichen, bewusst pragmatischen Syntax. Datumsregeln prüfen das Format, nicht die Kalendergültigkeit. Pfadregeln können abschließende Satzzeichen oder URL-Pfade miterfassen.

Die Regeln verwenden indexierte Ersetzungen mit eindeutigen Präfixen und abgestuften Prioritäten. Niedrigere Prioritätszahlen werden zuerst ausgeführt. Wenn zwei aktive Regeln denselben Geltungsbereich, Suchtyp, dasselbe Muster und dieselbe Priorität haben, meldet die Konfigurationsprüfung einen Konflikt.
