# Sicherheitskonzept nach BSI-Methodik – LogSanitizer

**Dokument-ID:** LS-SEC-001  
**Version:** 1.1  
**Stand:** 05.11.2026  
**Status:** Entwurf zur organisatorischen Prüfung und Freigabe  
**Gültige Produktbaseline:** LogSanitizer Anforderungen v2.8  
**Schutzbereich:** Anwendung LogSanitizer einschließlich Laufzeitumgebung, lokaler Datenhaltung, Benutzer- und Review-Prozess sowie optionaler Kommunikation im definierten Air-Gap-Netz

> **Wichtiger Geltungshinweis:** Dieses Dokument ist ein anwendungsspezifisches Sicherheitskonzept, das sich methodisch an den BSI-Standards 200-2 und 200-3 sowie dem IT-Grundschutz orientiert. Es ist keine BSI-Zertifizierung, kein Testat und kein vollständiger IT-Grundschutz-Check. Die organisationsspezifische Strukturanalyse, Schutzbedarfsfeststellung, Modellierung, Risikoakzeptanz und Umsetzungskontrolle müssen durch den Betreiber ergänzt und freigegeben werden. Die beschriebenen Maßnahmen sind teilweise Soll-Anforderungen und teilweise bereits im Entwicklungsstand vorhandene Kontrollen; der jeweilige Status ist ausdrücklich gekennzeichnet.

---

## 1. Zweck und Zielsetzung

LogSanitizer dient der lokalen Bereinigung von Anwendungs-Logdateien, bevor diese an Dritte, Hersteller oder andere nicht für die Originaldaten berechtigte Stellen weitergegeben werden. Die Anwendung erkennt und ersetzt anhand konfigurierbarer Regeln unter anderem IP-Adressen, Hostnamen, Benutzerkennungen, E-Mail-Adressen, personenbezogene Angaben, Zugangsdaten, Tokens, Dateipfade und interne Infrastrukturinformationen.

Ziele dieses Sicherheitskonzepts sind:

- Vertraulichkeit der Original-Logs, Mapping-Daten und Zugangsdaten wahren.
- Integrität und Nachvollziehbarkeit von Bereinigung, Prüfung, Freigabe und Export sicherstellen.
- Unbeabsichtigte Veröffentlichung von Originalen, fehlerhaften oder nicht freigegebenen Ergebnissen verhindern.
- Verfügbarkeit und zuverlässige Verarbeitung auch großer Dateien unterstützen.
- Risiken des bewusst eng begrenzten Einsatzmodells transparent machen und angemessen behandeln.

Das Sicherheitsniveau ist auf den vereinbarten Einsatzbereich auszurichten. Performance, Bedienbarkeit und Wartbarkeit haben neben der sicheren Verarbeitung einen hohen Stellenwert. Eine Hochsicherheitsplattform für beliebige Netze ist ausdrücklich nicht das Ziel.

## 2. Geltungsbereich und Betriebsgrenzen

### 2.1 Zugelassene Betriebsarten

**A. Standalone-Betrieb**

- Einzelner Windows- oder Linux-Laptop.
- Kein Netzwerkzugriff auf die Anwendung; Weboberfläche ausschließlich über Loopback (127.0.0.1 bzw. ::1).
- Lokale Benutzerkonten.
- Keine LDAP- oder SMTP-Abhängigkeit.
- Verarbeitung und Speicherung auf dem lokalen Gerät.

**B. Definiertes Air-Gap-Netz**

- Betrieb ausschließlich in einem organisatorisch und technisch abgegrenzten, vom Internet getrennten Netzwerk.
- Netzwerk-Bind-Adresse wird explizit auf eine vorgesehene Schnittstelle gesetzt.
- Zugriff nur von freigegebenen Clients und über die Firewall-Regeln des Betreibers.
- HTTPS für die Weboberfläche und LDAPS oder LDAP mit StartTLS für optionale Verzeichnisanmeldung.
- Optional LDAP/Active Directory zur Authentifizierung und Gruppenzuordnung sowie SMTP für Review-Benachrichtigungen.
- Kein Cloud-Dienst, CDN, externer API-Aufruf oder Internetzugriff zur Laufzeit.

### 2.2 Ausdrücklich ausgeschlossene Einsatzarten

Nicht zulässig im Rahmen dieses Konzepts sind:

- Betrieb im öffentlichen Internet oder in nicht vertrauenswürdigen Netzen.
- Freigabe der Anwendung an beliebige Netzwerksegmente.
- Nutzung als allgemeines DLP-, SIEM- oder vollständiges Data-Discovery-System.
- Annahme, dass eine erfolgreiche Regelprüfung alle sensiblen Inhalte zuverlässig erkennt.
- Verwendung als alleinige Schutzmaßnahme für Informationen mit besonders hohem oder sehr hohem Schutzbedarf ohne zusätzliche Risikoanalyse und Freigabe.

### 2.3 Systemgrenzen

Zum betrachteten Informationsverbund gehören:

1. LogSanitizer-Weboberfläche (React/TypeScript).
2. Backend und API (Python/FastAPI).
3. Regel- und Formatverarbeitung einschließlich Streaming.
4. Projekt-, Datei-, Mapping-, Lauf-, Review- und Audit-Daten in SQLite bzw. im lokalen Datenverzeichnis.
5. Importierte Originaldateien und erzeugte Bereinigungsergebnisse.
6. Lokale Windows-/Linux-Laufzeit, Benutzerkonten, Dateisystem und Sicherungsmedien.
7. Im Netzwerkprofil: Browser-Clients, Netzwerksegment, Firewall, TLS-Zertifikate, LDAP/AD und optional SMTP.

Nicht Bestandteil des Anwendungssystems sind die Quellsysteme, welche die Logs erzeugen, sowie die Zielsysteme der späteren Loganalyse. Deren Schutz und Berechtigungen verbleiben bei den jeweiligen Betreibern.

## 3. Methodische Grundlage und Annahmen

Das Konzept orientiert sich an folgenden BSI-Veröffentlichungen:

- BSI-Standard 200-2 – IT-Grundschutz-Methodik: Sicherheitskonzeption, Strukturanalyse, Schutzbedarfsfeststellung, Modellierung und IT-Grundschutz-Check.
- BSI-Standard 200-3 – Risikoanalyse auf der Basis von IT-Grundschutz: Gefährdungsübersicht, Risikoeinstufung, Risikobehandlung und Konsolidierung.
- IT-Grundschutz-Kompendium: als Referenz für die spätere Zuordnung geeigneter Bausteine und Anforderungen.

Für eine vollständige organisationsbezogene Anwendung der BSI-Methodik sind insbesondere die tatsächlichen Geschäftsprozesse, Datenarten, Schutzbedarfsträger, Räume, Geräte, Netzverbindungen, Zuständigkeiten und gesetzlichen Anforderungen des Betreibers aufzunehmen. Diese Informationen liegen dem Softwareprojekt nicht vollständig vor und werden deshalb nicht fingiert.

**Annahmen für die vorläufige Bewertung:**

- Die Anwendung wird von einer kleinen, benannten Nutzergruppe betrieben.
- Die zugrundeliegenden Logs können interne Betriebsinformationen und personenbezogene Daten enthalten.
- Die Originaldaten sind im Zweifel schutzwürdiger als die bereinigten Ausgaben.
- Das Endgerät befindet sich in einem kontrollierten physischen Umfeld.
- Betriebssystem, Browser und Netzwerkkomponenten werden vom Betreiber aktuell gehalten und administriert.
- Es gibt eine verantwortliche Stelle für Benutzer, Rollen, Regeländerungen, Freigaben, Backups und Sicherheitsvorfälle.

## 4. Schutzbedarfsfeststellung

Die folgende Einstufung ist eine **vorläufige anwendungsbezogene Einschätzung**. Sie muss anhand der konkreten Logs und Geschäftsprozesse vom Betreiber bestätigt werden.

| Objekt / Information | Vertraulichkeit | Integrität | Verfügbarkeit | Begründung |
|---|---|---|---|---|
| Original-Logdateien | hoch | mittel bis hoch | mittel | Können personenbezogene Daten, Zugangsdaten und interne Infrastrukturdetails enthalten. |
| Mapping-Daten | hoch | hoch | mittel | Ermöglichen die Rückzuordnung von Platzhaltern zu Originalwerten; Manipulation gefährdet Konsistenz. |
| Bereinigte Logdateien | mittel | hoch | mittel | Zur Weitergabe vorgesehen; unerkannt verbliebene Geheimnisse oder unbemerkte Änderungen können Schaden verursachen. |
| Regeldefinitionen und Quellprofile | mittel | hoch | mittel | Fehlerhafte oder manipulierte Regeln können sensible Werte durchlassen oder Daten verfälschen. |
| Benutzer-, Rollen- und Sitzungsdaten | hoch | hoch | mittel | Unberechtigte Rollenübernahme ermöglicht Zugriff, Änderung oder Freigabe. |
| Prüf- und Audit-Historie | mittel bis hoch | hoch | mittel | Muss Entscheidungen und Verantwortlichkeiten nachvollziehbar belegen. |
| Zugangsdaten, TLS-Schlüssel, LDAP-Bind-Geheimnis | sehr hoch | hoch | mittel | Kompromittierung kann Systemzugriff oder Identitätsmissbrauch ermöglichen. |
| Anwendung und Konfiguration | mittel | hoch | mittel | Manipulation kann Sicherheitskontrollen und Verarbeitung beeinflussen. |

**Vorläufiger Gesamtschutzbedarf:** Vertraulichkeit hoch, Integrität hoch, Verfügbarkeit normal bis mittel. Der Schutzbedarf der Zugangsdaten und Mapping-Daten ist gesondert als sehr hoch bzw. hoch zu behandeln. Ein abweichender Schutzbedarf einzelner Logquellen ist möglich und muss durch den Datenverantwortlichen festgelegt werden.

## 5. Datenarten und Datenfluss

### 5.1 Datenarten

- Original-Logs und importierte Dateien.
- Bereinigte Ausgabedateien.
- Projektmetadaten, Dateipfade und Prüfsummen bzw. Laufbezüge, soweit implementiert.
- Regeldefinitionen und Quellprofile.
- Projektbezogene Mapping-Zuordnungen.
- Benutzerkonten, Rollen, Sitzungen und Authentifizierungsmetadaten.
- Prüfentscheidungen, Kommentare, Exportereignisse und Audit-Metadaten.
- Optionale LDAP-/SMTP-Konfiguration und Zertifikatsmaterial.

### 5.2 Verarbeitungsablauf

1. Benutzer meldet sich an und wählt ein Projekt.
2. Originaldateien werden manuell oder über einen Ordnerimport registriert. Der Import startet keine Bereinigung.
3. Originale werden als unveränderte Eingaben behandelt.
4. Backend verarbeitet die Dateien streamend im internen Projektarbeitsbereich und wendet globale sowie quellspezifische Regeln an.
5. Technische Integritäts- und konfigurierte Restmusterprüfungen werden ausgeführt.
6. Bei zugewiesenem Prüfer ist eine bewusste menschliche Freigabe erforderlich. Ohne Prüferzuweisung kann nach bestandenen Pflichtprüfungen automatisch freigegeben werden.
7. Erst nach erfolgreicher Validierung und Freigabe kann der Bearbeiter den Export ausdrücklich starten: in einen auf seinem Arbeitsplatz gewählten Ordner oder als ZIP-Download.
8. Exportereignisse werden nachvollziehbar protokolliert.

Originale, zurückgewiesene, gestoppte und fehlgeschlagene Ergebnisse dürfen nicht in einen regulären Export gelangen.

### 5.3 Datenminimierung

- Logs und Ausschnitte dürfen nicht in normale Anwendungs-, Fehler- oder Auditmeldungen kopiert werden.
- Audit-Einträge enthalten Identität, Zeitpunkt, Aktion, Entscheidung, Kommentar und fachliche Bezüge, soweit erforderlich, nicht aber unnötige Loginhalte.
- E-Mail-Benachrichtigungen enthalten nur die für den Review erforderlichen Hinweise und keine Loginhalte, Mapping-Tabellen oder Geheimnisse.
- Diagnosepakete und Supportdaten sind vor Weitergabe auf vertrauliche Inhalte zu prüfen.

## 6. Rollen und Verantwortlichkeiten

Die Anwendung sieht folgende Rollen vor. Eine Person darf bei geringer Personalstärke mehrere Rollen übernehmen; organisatorische Funktionstrennung bleibt dennoch zu bevorzugen.

| Rolle | Aufgaben | Sicherheitsrelevante Grenzen |
|---|---|---|
| Administrator | Benutzer, Rollen, System- und Deployment-Konfiguration | Vergibt Rechte; prüft Änderungen an sicherheitsrelevanten Einstellungen. |
| Rule Owner / Regelverantwortlicher | Regeln und Quellprofile erstellen, ändern und pflegen | Regeländerungen nachvollziehbar versionieren und vor produktiver Nutzung testen. |
| Processor / Bearbeiter | Projekte und Dateien importieren, Bereinigung starten, Ergebnisse exportieren | Export nur für freigegebene und erfolgreich validierte Ergebnisse. |
| Reviewer / Prüfer | Bereinigte Ergebnisse prüfen, suchen, vergleichen, freigeben, zurückgeben oder stoppen | Keine Freigabe bei ungeklärten Auffälligkeiten; Kommentare bei Rückgabe/Stop dokumentieren. |
| Approver / Freigeber | Formale Freigabe gemäß zugewiesener Berechtigung | Nur nach Prüfung der Pflichtstatus und der fachlichen Entscheidung freigeben. |

**Soll-Regel:** Kritische Änderungen an Regeln, Rollen, LDAP-Gruppenzuordnungen und Deployment-Einstellungen sind nur autorisierten Personen gestattet. Die konkrete Berechtigungsmatrix ist vor Produktivbetrieb gegen sämtliche API-Endpunkte zu prüfen.

## 7. Bedrohungs- und Risikoanalyse

Bewertungsskala: Eintrittswahrscheinlichkeit (E) und Schadensausmaß (S) jeweils niedrig / mittel / hoch. Die Einstufung ist eine vorläufige qualitative Bewertung für das beschriebene Einsatzmodell, keine statistische Messung.

| ID | Gefährdung | E | S | Risiko | Behandlung / Maßnahme |
|---|---|---|---|---|---|
| R1 | Sensible Daten verbleiben unentdeckt in der bereinigten Datei | mittel | hoch | hoch | Regeltests, Restmusterprüfung, Stichproben, Vergleich Original/bereinigt, menschliche Freigabe, dokumentierte Grenzen. |
| R2 | Unberechtigter lokaler Zugriff auf Originale oder Mapping-Daten | mittel | hoch | hoch | Gerätezugang schützen, persönliche OS-Konten, Bildschirmsperre, Datenträger-/Backup-Schutz nach Betreiberstandard. Mapping-Datenbank ist nicht zusätzlich verschlüsselt. |
| R3 | Fehlerhafte oder manipulierte Regel entfernt bzw. ersetzt falsche Inhalte | mittel | hoch | hoch | Rollenbegrenzung, Regeltests/Vorschau, Versionskontrolle, Vier-Augen-Prinzip bei kritischen Regeln, Audit. |
| R4 | Unberechtigte Anmeldung oder Rollenübernahme | mittel | hoch | hoch | Individuelle Konten, starke Passwörter bzw. LDAP, Sitzungsbegrenzung, Fehlversuchssperre, CSRF-Schutz, serverseitige Rollenprüfung. |
| R5 | Original, fehlerhafte oder zurückgewiesene Datei wird exportiert | niedrig bis mittel | hoch | mittel/hoch | Statusmodell, erneute Exportprüfung, expliziter Export durch Bearbeiter, Dateiliste und Exportaudit; Negativtests. |
| R6 | Manipulation oder Verlust von Review-/Audit-Daten | mittel | mittel bis hoch | mittel/hoch | Schreibrechte begrenzen, regelmäßige Backups, Wiederherstellungstests, administrative Änderungen protokollieren. |
| R7 | Netzwerkzugriff außerhalb des Air-Gap-Verbunds | niedrig bei korrekter Konfiguration | hoch | mittel | Loopback im Standalone, explizite Netzwerk-Bind-Adresse, Firewall-Allowlist im Zielnetz, HTTPS, Netzprüfung vor Freigabe. |
| R8 | Kompromittierung von LDAP-/SMTP-Geheimnissen oder TLS-Schlüsseln | niedrig bis mittel | hoch | mittel/hoch | Geheimnisse nur lokal über Umgebungsvariablen/Secret-Handling, keine Ablage im Repository oder Paket, Schlüsselzugriff organisatorisch begrenzen, Rotation. |
| R9 | Regex-/Dateiverarbeitungsfehler führt zu DoS oder unvollständigem Ergebnis | mittel | mittel bis hoch | mittel/hoch | Timeout-fähige Regex, Streaming, Fehlerstatus, Abbruch, Ressourcenüberwachung; globales Ressourcenbudget bleibt zu prüfen. |
| R10 | Schadsoftware oder kompromittierter Host liest/verändert Daten | mittel | hoch | hoch | Gehärteter und aktualisierter Host, Endpoint-Schutz nach Betreiberstandard, eingeschränkte Benutzerrechte, vertrauenswürdige Softwarequellen. |
| R11 | Veraltete oder manipulierte portable Binärdatei | mittel | hoch | hoch | Releases nur aus kontrolliertem Buildprozess, Herkunft/Hash prüfen, Abhängigkeiten aktualisieren, Artefakte und Build-Commit dokumentieren. |
| R12 | Backup oder Supportkopie enthält Originaldaten/Mappings und wird offengelegt | mittel | hoch | hoch | Backup-Schutz und Zugriff nach Betreiberstandard, Aufbewahrungsfristen, sichere Löschung und Wiederherstellungstests. |

### 7.1 Besondere Restrisiken

1. **Keine vollständige automatische Erkennung:** Eine bestandene Validierung belegt nur, dass konfigurierte Prüfungen erfolgreich waren. Sie ist kein Beweis, dass sämtliche personenbezogenen Daten, Geheimnisse oder internen Informationen erkannt wurden.
2. **Mapping-Daten unverschlüsselt:** Mapping-Zuordnungen liegen in der lokalen SQLite-Datenbank. Personen mit entsprechendem Zugriff auf das Datenverzeichnis können sie auslesen. Dies ist eine bewusste Produktentscheidung der Baseline v2.8.
3. **Lokaler Host als Vertrauensanker:** Ein kompromittiertes Betriebssystem, lokaler Administrator oder physischer Angreifer kann auf Daten zugreifen oder Prozesse manipulieren.
4. **Kein allgemeiner Netzwerkbetrieb:** Das Sicherheitskonzept gilt nicht für öffentliche oder nicht vertrauenswürdige Netze.
5. **Kein vollständiges Ressourcenlimit:** Regex-Timeouts und Streaming verhindern nicht jede Form von Ressourcenerschöpfung oder Überlastung.
6. **Keine unabhängige Sicherheitsprüfung:** Die vorliegenden CI- und Smoke-Tests sind keine Penetrationsprüfung, kein vollständiger API-Autorisierungstest und keine Zertifizierung.

## 8. Sicherheitsmaßnahmen und Soll-Anforderungen

### 8.1 Organisation und Betrieb

- Betreiber benennt Systemverantwortlichen, fachlichen Datenverantwortlichen und Administrator.
- Nutzung nur für freigegebene Zwecke und Datenquellen.
- Rollen werden nach Aufgaben vergeben und regelmäßig überprüft.
- Regeländerungen werden vor Einsatz getestet und nachvollziehbar dokumentiert.
- Bei kritischen Regeln oder besonders schutzwürdigen Logs ist eine zweite Person zur Prüfung vorzusehen.
- Betriebs- und Sicherheitsvorfälle werden nach dem Incident-Management des Betreibers behandelt.

### 8.2 Endgerät und Betriebssystem

- Unterstützte Windows-/Linux-Systeme erhalten Sicherheitsupdates nach dem Patchmanagement des Betreibers.
- Anmeldung erfolgt über persönliche Betriebssystemkonten; automatische Anmeldung ist zu vermeiden.
- Bildschirm wird bei Abwesenheit gesperrt.
- Datenträger und Sicherungsmedien sind entsprechend dem Schutzbedarf zu schützen; eine vorhandene Betriebssystem-/Datenträgerverschlüsselung wird empfohlen.
- Unnötige Dienste, Freigaben und Netzwerkadapter werden deaktiviert bzw. kontrolliert.
- Nur vertrauenswürdige portable Pakete und geprüfte Updates verwenden.
- Lokale Benutzerrechte werden auf das notwendige Maß begrenzt.

### 8.3 Anwendung, Authentifizierung und Sitzungen

- Standalone muss auf Loopback beschränkt bleiben.
- Im Netzwerkprofil muss eine konkrete vorgesehene Bind-Adresse verwendet werden.
- Jeder Benutzer erhält ein eigenes Konto; Sammelkonten sind zu vermeiden.
- Lokale Passwörter müssen ausreichend stark sein; der Betreiber legt eine Passwort- und Kontenrichtlinie fest.
- LDAP/AD wird nur über LDAPS oder StartTLS mit Zertifikatsprüfung angebunden.
- LDAP-Rollen werden explizit aus freigegebenen Gruppen abgeleitet. Ein lokaler Passwort-Fallback bei LDAP-Betrieb ist nicht vorgesehen.
- Sitzungen sind zeitlich begrenzt; zustandsändernde Anfragen sind gegen CSRF abzusichern.
- Serverseitige Autorisierung ist für jede API-Funktion durchzusetzen. UI-Ausblendung allein ist keine Berechtigungskontrolle.
- Rollen- und Rechteänderungen sind nachvollziehbar zu protokollieren.

### 8.4 Netzwerk und Kommunikation

- Netzwerkmodus nur nach dokumentierter Freigabe des Air-Gap-Netzes.
- Firewall erlaubt nur notwendige Client-zu-Server-Verbindungen.
- HTTPS ist verpflichtend; Zertifikate müssen aus einer vom Betreiber kontrollierten Vertrauenskette stammen.
- LDAP-Kommunikation ist verschlüsselt und serverseitig zu verifizieren.
- SMTP verwendet STARTTLS oder SSL; Zugangsdaten werden nicht in JSON-Konfiguration, Quellcode oder portable Pakete geschrieben.
- SMTP-Ausfall darf die Bereinigung nicht blockieren; ausstehende Benachrichtigungen sind organisatorisch anderweitig nachzuverfolgen.
- Internetverbindungen sind im Zielbetrieb technisch zu unterbinden bzw. nachweislich nicht erforderlich.

### 8.5 Dateien, Verarbeitung und Export

- Originaldateien bleiben unverändert; die Anwendung darf sie nicht automatisch verschieben oder löschen.
- Verarbeitung erfolgt streamend und mit begrenzten Puffern.
- Fehlgeschlagene oder abgebrochene Läufe dürfen nicht als erfolgreich oder freigegeben markiert werden.
- Pflichtvalidierung und menschliche Freigabe sind getrennte Zustände.
- Rückgewiesene, gestoppte und fehlgeschlagene Läufe sind vom regulären Export ausgeschlossen.
- Export wird durch den Bearbeiter ausdrücklich gestartet und erneut serverseitig geprüft.
- Vorhandene Zieldateien dürfen nicht stillschweigend überschrieben werden.
- ZIP-Erstellung und Übertragung sind speicherschonend umzusetzen.
- Exportereignisse enthalten mindestens Benutzer, Zeitpunkt, Methode und Dateibezug.

### 8.6 Regeln und Mapping

- Regeldefinitionen werden versioniert und vor produktiver Nutzung getestet.
- Globale Regeln und Quellprofile werden getrennt verwaltet.
- Regelprioritäten und Konflikte sind nachvollziehbar.
- Mapping-Zuordnungen sind projektbezogen und müssen über Dateien und Läufe konsistent bleiben.
- Mapping-Datenbank und Projektarbeitsbereich sind in Backup- und Löschprozesse einzubeziehen.
- Die Datenbank wird gemäß Baseline v2.8 nicht zusätzlich durch eine separate Anwendungsschlüsseldatei verschlüsselt. Der Zugriffsschutz erfolgt über den Schutz des Endgeräts und des lokalen Datenverzeichnisses.

### 8.7 Protokollierung und Audit

- Anmeldungen, relevante administrative Änderungen, Regeländerungen, Verarbeitungsstatus, Review-Entscheidungen und Exporte werden nachvollziehbar protokolliert.
- Keine Passwörter, Tokens, vollständigen Logzeilen oder Mapping-Werte in Audit- und Fehlerprotokollen.
- Audit-Daten sind vor unberechtigter Änderung und Löschung zu schützen.
- Aufbewahrungsfristen, Zugriff und Löschung legt der Betreiber fest.
- Zeitbasis des Systems ist korrekt zu halten; Zeitabweichungen können die Nachvollziehbarkeit beeinträchtigen.

### 8.8 Backup und Wiederherstellung

- Regelmäßige Sicherung des gesamten erforderlichen Datenbestands: Datenbank, Projekte, Mapping-Zuordnungen, Regelkonfigurationen und Audit-/Review-Daten.
- Sicherungen enthalten möglicherweise Originaldaten und sind entsprechend zu schützen.
- Backup-Zugriff ist auf berechtigte Personen zu beschränken.
- Wiederherstellung ist vor Produktivbetrieb und anschließend regelmäßig zu testen.
- Sicherungen und temporäre Dateien sind nach festgelegten Aufbewahrungsfristen sicher zu löschen.

### 8.9 Softwarelieferkette und Updates

- Builds werden reproduzierbar bzw. nachvollziehbar aus einem festgehaltenen Commit erzeugt.
- Windows- und Linux-Pakete werden auf den jeweiligen Plattformen gebaut und mit Smoke-Tests geprüft.
- Abhängigkeiten werden regelmäßig auf bekannte Schwachstellen geprüft und aktualisiert.
- Release-Artefakte sind mit Commit, Build-Lauf und Prüfsumme zu dokumentieren.
- Updates werden vor Installation in einer Testumgebung geprüft und mit einem Backup der Anwendungsdaten kombiniert.
- GitHub dient als Entwicklungs- und Quellcodeplattform; der produktive Offline-Betrieb darf keine Verbindung zu GitHub benötigen.

## 9. Entwicklungsstand und Nachweisstatus

Die konkrete Zuordnung von Sicherheitszielen zu Testfällen, erwarteten Ergebnissen, Nachweisen und Abnahmestatus ist in der ergänzenden [Technischen Sicherheits- und Abnahmematrix LS-SEC-002](ABNAHMEMATRIX.md) festgelegt. Diese Matrix ist Bestandteil dieses Sicherheitskonzepts und bei jeder sicherheitsrelevanten Änderung mitzuführen.

Die nachfolgende Tabelle trennt implementierte bzw. dokumentierte Funktionen von offenen Abnahmen. Ein Eintrag „vorhanden“ ersetzt keine unabhängige Prüfung.

| Kontrolle | Stand laut Projektunterlagen | Erforderlicher Nachweis vor Produktivbetrieb |
|---|---|---|
| Standalone Loopback-Bindung | implementiert und konfigurationsseitig validiert | Test auf Windows und Linux; Zugriff von anderem Host muss scheitern. |
| Netzwerkprofil mit TLS-Pflicht | implementiert | Zertifikats- und Firewall-Abnahme im Zielnetz. |
| Lokale Anmeldung / Rollen | implementiert | vollständige Negativtests für jede API-Route und jede Rolle. |
| LDAP/AD und Gruppenzuordnung | implementiert | Tests mit realem Zielverzeichnis, Rollen und Zertifikatskette. |
| SMTP-Benachrichtigung | optional implementiert | Zustelltest und organisatorischer Ersatzprozess bei Ausfall. |
| Streaming und große Dateien | implementiert; synthetischer 5-GiB-CI-Lauf dokumentiert | repräsentative Logs auf Zielhardware, Laufzeit/RAM und Ergebnisqualität bewerten. |
| Regel- und Restmusterprüfung | konfigurationsbasiert | fachliche Testkataloge je Quellprofil; False-Negative-Risiko bewerten. |
| Review, Freigabe und Audit | implementiert | Ende-zu-Ende- und Manipulations-/Berechtigungstests. |
| Export nur freigegebener Ergebnisse | Anforderung und Implementierung vorhanden | Negativtests für zurückgewiesene, gestoppte, fehlgeschlagene und unvollständige Läufe. |
| Backup/Wiederherstellung | organisatorisch festzulegen | dokumentierter erfolgreicher Wiederherstellungstest. |
| Unabhängiger Penetrationstest | nicht nachgewiesen | abhängig von Schutzbedarf und Einsatzorganisation entscheiden. |

**Bekannte Einschränkungen aus der Sicherheitsbewertung:** Keine vollständige Negativprüfung aller API-Routen gegen jede Rolle; kein globales Job-/CPU-Budget; keine vollständige Erkennung aller sensiblen Daten; echte LDAP-/SMTP-Zielumgebung und Zielhardware müssen separat abgenommen werden.

## 10. Sicherheitsvorfälle und Notfallmaßnahmen

Bei Verdacht auf unberechtigten Zugriff, Datenabfluss, kompromittierte Zugangsdaten, manipulierte Regeln oder fehlerhafte Freigabe gilt mindestens:

1. Netzwerkzugriff auf die Anwendung unterbrechen bzw. Anwendung kontrolliert stoppen.
2. Keine weiteren Exporte durchführen.
3. Betroffene Projekte, Zeiträume, Benutzer, Läufe und Exportereignisse identifizieren.
4. Relevante Beweisdaten sichern, ohne Original-Logs unnötig zu vervielfältigen.
5. Zugangsdaten, LDAP-Bind-Geheimnisse oder Zertifikate bei Bedarf sperren bzw. erneuern.
6. Verantwortliche Stelle und Informationssicherheitsbeauftragten informieren.
7. Betroffene Exporte identifizieren und Empfänger über erforderliche Maßnahmen informieren.
8. Wiederanlauf erst nach Ursachenklärung, Integritätsprüfung und Freigabe durch die zuständige Stelle.

Gesetzliche Melde- und Informationspflichten sind durch die Organisation anhand ihrer konkreten Betroffenheit gesondert zu prüfen.

## 11. Abnahme- und Freigabekriterien

Vor produktiver Nutzung müssen mindestens folgende Punkte dokumentiert erfüllt sein:

- [ ] Betreiber, Systemverantwortlicher und Datenverantwortlicher sind benannt.
- [ ] Zulässige Datenquellen und Datenarten sind festgelegt.
- [ ] Schutzbedarfsfeststellung wurde organisatorisch bestätigt.
- [ ] Standalone- oder Air-Gap-Betriebsart ist eindeutig festgelegt.
- [ ] Netzwerkmodus: Segmentierung, Firewall, TLS und Clientzugriff sind geprüft.
- [ ] Benutzer, Rollen und Berechtigungen wurden einschließlich negativer Zugriffstests geprüft.
- [ ] LDAP-/AD-Gruppenmapping und Zertifikate wurden im Zielnetz getestet, falls aktiviert.
- [ ] Regelwerke wurden anhand repräsentativer Original-Logs getestet.
- [ ] Restmusterprüfung und manuelle Stichproben sind fachlich abgenommen.
- [ ] Originaldateien bleiben unverändert; fehlgeschlagene Läufe können nicht exportiert werden.
- [ ] Review-, Rückgabe-, Freigabe- und Audit-Abläufe wurden Ende zu Ende getestet.
- [ ] Exportordner und ZIP-Download wurden einschließlich großer Dateien geprüft.
- [ ] Backup und Wiederherstellung wurden erfolgreich getestet.
- [ ] Betriebssystem-Updates, Virenschutz/Endpoint-Schutz und physischer Zugriff sind geregelt.
- [ ] Restrisiken wurden vom zuständigen Risikoeigner ausdrücklich akzeptiert.
- [ ] Betriebsanweisung und Incident-Kontakte liegen offline vor.

**Freigabeentscheidung:** Die Anwendung darf erst nach dokumentierter Abnahme durch den Betreiber produktiv eingesetzt werden. Eine technische CI-Erfolgsmeldung allein ist keine Betriebsfreigabe.

## 12. Restrisiken und Risikoakzeptanz

Folgende Restrisiken werden durch die Produktbaseline bewusst nicht vollständig technisch beseitigt:

- Mapping-Daten liegen unverschlüsselt in SQLite.
- Ein lokaler Administrator oder ein kompromittierter Host kann auf lokale Daten zugreifen.
- Regelbasierte Erkennung kann unbekannte oder nicht konfigurierte sensible Inhalte übersehen.
- Ein menschlicher Prüfer kann Inhalte falsch bewerten.
- Ohne globale Ressourcenbudgets können ungünstige Eingaben weiterhin Ressourcen stark beanspruchen.
- Die Sicherheit des Netzwerkbetriebs hängt von der konkreten Air-Gap-Umgebung und deren Administration ab.

Diese Risiken sind vom Betreiber anhand des tatsächlichen Schutzbedarfs zu bewerten. Bei nicht akzeptablem Restrisiko ist der Einsatz zu unterlassen oder durch zusätzliche organisatorische bzw. technische Maßnahmen zu ergänzen. Eine pauschale Risikoakzeptanz durch dieses Dokument erfolgt ausdrücklich nicht.

## 13. Pflege und Aktualisierung

Das Konzept ist mindestens jährlich sowie anlassbezogen zu überprüfen, insbesondere bei:

- Änderung der Anforderungen oder des Betriebsmodells.
- Einführung neuer Datenquellen oder Dateiformate.
- Änderung von Rollen, Authentifizierung oder LDAP-Gruppen.
- Änderung von Netzwerksegmenten, TLS-Zertifikaten oder SMTP.
- Wesentlichen Änderungen an Regel-Engine, Export, Datenhaltung oder Audit.
- Bekanntwerden relevanter Sicherheitslücken oder Sicherheitsvorfällen.
- Erhöhung des Schutzbedarfs.

Änderungen am Konzept werden versioniert und durch die zuständige Stelle freigegeben.

## 14. Quellen und Referenzen

1. Bundesamt für Sicherheit in der Informationstechnik (BSI), **BSI-Standard 200-2 – IT-Grundschutz-Methodik**: https://www.bsi.bund.de/SharedDocs/Downloads/DE/BSI/Grundschutz/BSI_Standards/standard_200_2.pdf
2. Bundesamt für Sicherheit in der Informationstechnik (BSI), **BSI-Standard 200-3 – Risikoanalyse auf der Basis von IT-Grundschutz**: https://www.bsi.bund.de/SharedDocs/Downloads/DE/BSI/Grundschutz/BSI_Standards/standard_200_3.pdf
3. BSI, **IT-Grundschutz-Kompendium**: https://www.bsi.bund.de/grundschutz
4. Projektinterne Referenzen: `docs/REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, `docs/SECURITY_REVIEW.md`, `SECURITY.md`.

---

## Anlage A – Betreiberbezogene Ergänzungen (auszufüllen)

| Angabe | Eintrag |
|---|---|
| Organisation / Betreiber | [eintragen] |
| Fachlicher Datenverantwortlicher | [eintragen] |
| Systemverantwortlicher | [eintragen] |
| Informationssicherheitsbeauftragter | [eintragen] |
| Betriebsart | [Standalone / Air-Gap] |
| Standort / Raum | [eintragen] |
| Windows-/Linux-Versionen | [eintragen] |
| Netzwerksegment / erlaubte Clients (nur Air-Gap) | [eintragen] |
| Zulässige Logquellen und Schutzbedarf | [eintragen] |
| Datenaufbewahrung / Löschfristen | [eintragen] |
| Backup-Verantwortlicher / Sicherungsziel | [eintragen] |
| Incident-Kontakt | [eintragen] |
| Risikoakzeptierende Stelle | [eintragen] |
| Datum der letzten Abnahme | [eintragen] |

## Anlage B – Versionshistorie

| Version | Datum | Änderung |
|---|---|---|
| 1.0 | 05.11.2026 | Erster anwendungsspezifischer Entwurf auf Basis der Anforderungen v2.8 und der dokumentierten Sicherheitsbewertung. |
| 1.1 | 05.11.2026 | Verknüpfung mit der technischen Sicherheits- und Abnahmematrix LS-SEC-002. |
