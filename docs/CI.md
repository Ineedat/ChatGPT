# CI-Strategie

## Ziel

Die normale Entwicklungs-CI soll schnell Rückmeldung zu Codeänderungen geben. Zeit- und ressourcenintensive Integrationsprüfungen werden weiterhin ausgeführt, aber gezielt am Ende eines Meilensteins oder bei einem Release.

## Stufe 1: schnelle CI bei jedem Push und Pull Request

Workflow: `.github/workflows/ci.yml`

- Backend-Test-Suite auf Linux.
- Gezielter Backend-Regressionslauf auf Windows.
- Ruff-Linting auf beiden Betriebssystemen.
- Frontend-Tests und Produktionsbuild.
- Keine 5-GiB-Benchmarks und keine PyInstaller-Paketierung.

Diese Prüfungen müssen bei jedem Push und Pull Request erfolgreich sein.

## Stufe 2: Meilensteinprüfung bei Bedarf

Workflow: `.github/workflows/milestone-validation.yml`

Manueller Start in GitHub unter **Actions → Milestone validation → Run workflow**. Als Branch ist der zu prüfende Meilenstein-Stand auszuwählen.

- Synthetischer 5-GiB-Streaming-Benchmark auf Linux (standardmäßig aktiviert).
- Portable PyInstaller-Builds auf Windows und Linux.
- Standalone- und HTTPS-Netzwerk-Smoke-Tests für beide Pakete.
- Portable Build-Artefakte werden als Actions-Artefakte für 30 Tage bereitgestellt. Der Benchmark-Bericht ist im Job-Log sichtbar; die mehrere GiB großen synthetischen Eingabe-/Ausgabedateien werden ausdrücklich nicht hochgeladen.

Der 5-GiB-Lauf kann beim manuellen Start über die Eingabe deaktiviert werden, wenn ausschließlich Paketierung und Smoke-Tests geprüft werden sollen.

Die Meilensteinprüfung wird nach Abschluss eines Meilensteins sowie zusätzlich nach Änderungen an Streaming-Kern, Laufzeitabhängigkeiten, Start-/Deployment-Konfiguration oder Paketierung gestartet.

## Stufe 3: Release

Der bestehende Workflow `.github/workflows/release.yml` bleibt unverändert. Ein Versions-Tag baut und prüft die portablen Windows-/Linux-Pakete und veröffentlicht sie als Release-Artefakte.

## Abgrenzung

- CI-Benchmarkdaten sind synthetische Referenzwerte und kein Ersatz für Messungen auf der tatsächlichen Zielhardware.
- Smoke-Tests prüfen den lokalen Start und die grundlegende HTTP-/HTTPS-Erreichbarkeit. Sie ersetzen keine echte LDAP/AD- oder SMTP-Integration in der Air-Gap-Umgebung.
- Die spätere Zielsystem-Abnahme bleibt ein eigener dokumentierter Freigabeschritt.
