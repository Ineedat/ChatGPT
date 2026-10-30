# Performance-Abnahme

## Reproduzierbarer 5-GiB-Test

Der Benchmark erzeugt ausschließlich synthetische Logzeilen und misst die vollständige Bereinigung einschließlich der erneuten Ausgabeprüfung. Es werden keine produktiven Logdateien benötigt.

Linux:
```bash
python -m pip install -e "backend[dev]"
python packaging/benchmark_sanitizer.py --size-gib 5 --work-dir /var/tmp/logsanitizer-benchmark
```

Windows (PowerShell):
```powershell
py -m pip install -e "backend[dev]"
py packaging/benchmark_sanitizer.py --size-gib 5 --work-dir C:\LogSanitizer-Benchmark
```

Für einen kurzen Funktionstest kann `--size-gib 0.01` verwendet werden. Die CI führt diesen kleinen Lauf unter Windows und Linux aus und zusätzlich einen vollständigen 5-GiB-Lauf mit synthetischen 512-Byte-Datensätzen auf einem GitHub-gehosteten Linux-Runner. Dieser Runner-Lauf ist ein reproduzierbarer Referenzwert, ersetzt aber nicht die Messung auf der tatsächlichen Zielhardware.

## Messwerte

Der JSON-Bericht enthält Plattform und Python-Version, Eingabe-/Ausgabegröße, Wandzeit, CPU-Zeit, Durchsatz in MiB/s, Python-Tracemalloc-Spitze bei kleinen Läufen, maximalen Prozess-RSS (soweit verfügbar), Zeilen, Ersetzungen und Validierungsstatus. Beim 5-GiB-Lauf wird Tracemalloc bewusst deaktiviert, damit die Messung nicht durch die Speicherinstrumentierung verzerrt wird; dort ist der Prozess-RSS maßgeblich.

## Abnahmeprotokoll

Den 5-GiB-Lauf auf jeder tatsächlichen Zielplattform mindestens dreimal auf einem möglichst unbelasteten Gerät ausführen. Netzbetrieb, Energiesparmodus, Dateisystem und Virenscannerzustand dokumentieren.

| Messwert | Abnahmeanforderung |
|---|---|
| Dateigröße | mindestens 5 GiB |
| Integrität | `validated=true`, Quelldatei unverändert |
| Speicher | Prozess-RSS dokumentieren; Python-Tracemalloc separat mit dem kleinen CI-Lauf prüfen |
| Laufzeit | Wandzeit und CPU-Zeit dokumentieren |
| Durchsatz | MiB/s dokumentieren |
| Bedienbarkeit | UI während des Laufs bedienen; Statusaktualisierung und Abbruch messen |
| Wiederherstellung | Prozessabbruch simulieren; Lauf muss als unterbrochen gelten und darf nicht freigabefähig sein |

Es wird kein pauschaler Durchsatzwert versprochen: Datenträger, CPU, Dateisystem, Regelanzahl und Regex-Komplexität beeinflussen das Ergebnis. Die produktive Abnahme ist erst abgeschlossen, wenn die Messwerte auf den tatsächlichen Windows-/Linux-Zielgeräten vorliegen.

## Interpretation

- Python-Tracemalloc erfasst Python-allokierte Speicherbereiche, nicht alle nativen Bibliotheks- oder Betriebssystempuffer.
- Der maximale Prozess-RSS ist der bessere Gesamtindikator; auf manchen Plattformen kann dieser Wert fehlen.
- Der Durchsatz beinhaltet die zweite vollständige Lesepassage für Ausgabevalidierung und Restmustersuche.
- Der Benchmark misst die Text-Streaming-Pipeline. JSON-Dokumente und JSON Lines haben zusätzliches Parsing und sollten mit repräsentativen synthetischen Beispielen separat gemessen werden.


## Gemessener CI-Referenzlauf (2026-10-30)

Der vollständige synthetische 5-GiB-Lauf wurde in GitHub Actions auf einem gehosteten Linux-Runner erfolgreich ausgeführt (Python 3.11.17, Linux 7.0.0-1017-azure-x86_64, Lauf #41128457176).

| Messwert | Ergebnis |
|---|---:|
| Eingabe | 5,00 GiB (5.368.709.120 Byte) |
| Ausgabe | 5.379.194.880 Byte |
| Wandzeit | 96,806 s |
| CPU-Zeit | 93,708 s |
| Durchsatz | 52,89 MiB/s |
| Maximaler Prozess-RSS | 40.443.904 Byte (ca. 38,6 MiB) |
| Verarbeitete Zeilen | 10.485.760 |
| Ersetzungen | 10.485.760 |
| Ausgabevalidierung | erfolgreich |

Der Lauf verwendete synthetische 512-Byte-Logeinträge mit einer einfachen Ersetzungsregel. Tracemalloc war für diesen großen Lauf deaktiviert, damit die Instrumentierung die Laufzeit nicht verzerrt. Die Python-Tracemalloc-Messung erfolgt separat im kleinen CI-Benchmark. Diese Werte sind ein CI-Referenzpunkt, keine zugesicherte Leistung auf dem Zielgerät.
