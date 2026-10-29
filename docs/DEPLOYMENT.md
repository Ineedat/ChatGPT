# Deployment und portabler Betrieb

LogSanitizer ist für zwei klar abgegrenzte Betriebsarten vorgesehen: einen einzelnen Windows-/Linux-Laptop ohne Internetverbindung oder ein ausdrücklich definiertes, isoliertes Air-Gap-Netz. Ein Betrieb im öffentlichen Internet oder in nicht vertrauenswürdigen Netzen ist nicht vorgesehen.

Die zentrale Deployment-Konfiguration liegt in `config/deployment.json`; die Vorlage ist `config/deployment.example.json`. Im portablen Paket wird eine Standardkonfiguration mitgeliefert. Alternativ kann über `LOGSANITIZER_CONFIG` eine externe Konfigurationsdatei angegeben werden. Relative Pfade werden grundsätzlich relativ zum Speicherort der Konfigurationsdatei interpretiert.

## Standalone-Laptop

- Profil: `standalone`
- Bind-Adresse: `127.0.0.1` (nur lokaler Zugriff)
- Anmeldung: lokale Benutzerkonten
- LDAP und SMTP: nicht erforderlich
- Internetzugriff: nicht erforderlich

Das Programm wird unter Windows über `LogSanitizer.exe`, unter Linux über `./LogSanitizer` gestartet. Die Oberfläche wird lokal bereitgestellt und ist standardmäßig unter `http://127.0.0.1:8000` erreichbar.

Der erste Administrator wird einmalig über `LogSanitizer.exe --create-admin` beziehungsweise `./LogSanitizer --create-admin` angelegt. Benutzer und Rollen werden anschließend in der Anwendung verwaltet.

## Isoliertes Air-Gap-Netz

Für den Netzwerkbetrieb wird eine konkrete, für die vorgesehenen Clients erreichbare Schnittstellenadresse in `server.bind_host` konfiguriert. Der Netzwerkbetrieb bleibt auf das definierte isolierte Netz beschränkt; Firewall-Regeln sollen den Zugriff auf die vorgesehenen Clients begrenzen.

Die Anmeldung kann über lokale Benutzerkonten oder optional über LDAP/Active Directory erfolgen. Bei LDAP werden Server, Suchbasis und Gruppenzuordnung zu den LogSanitizer-Rollen konfiguriert. SMTP kann optional für Benachrichtigungen über ausstehende Reviews und Rückgaben aktiviert werden. Ohne LDAP und SMTP bleibt die Anwendung auch im isolierten Netz nutzbar.

TLS kann entsprechend der konkreten Netzwerkinfrastruktur eingesetzt werden. Es ist kein Produktziel, für einen vollständig isolierten, kontrollierten Air-Gap-Betrieb eine komplexe Zertifikats- und Geheimnisverwaltung zwingend vorauszusetzen. Die Netzfreigabe und die konkrete Transportabsicherung müssen zur jeweiligen Umgebung passen.

## Daten, Mapping und Backups

Projekte, importierte Dateimetadaten, Review-Informationen und Mapping-Zuordnungen werden lokal in SQLite gespeichert. Die Mapping-Zuordnungen sind projektbezogen: derselbe Originalwert erhält innerhalb eines Projekts über mehrere Dateien hinweg denselben Ersatzwert.

Neue Mapping-Einträge werden in der v2.8-Implementierung direkt in der lokalen SQLite-Datenbank gespeichert; eine separate Schlüsseldatei wird für den laufenden Betrieb nicht mehr angelegt. Bereits vorhandene verschlüsselte Mapping-Datenbanken werden beim ersten Zugriff einmalig migriert. Dafür muss die bisherige `mappings.key` im selben Datenverzeichnis vorhanden sein. Nach erfolgreicher Migration wird sie entfernt. **Vor dem ersten Start mit dieser Version unbedingt Datenbank und bisherige Schlüsseldatei gemeinsam sichern.** Fehlt der alte Schlüssel oder ist ein Eintrag beschädigt, wird die Migration abgebrochen und die alte Datenbank bleibt erhalten.

Vor Updates oder Migrationen ist eine Sicherung des gesamten Datenverzeichnisses anzulegen. Die Sicherung muss insbesondere die SQLite-Dateien und – solange die bestehende Verschlüsselungsimplementierung verwendet wird – die zugehörige Schlüsseldatei enthalten. Ein Wiederherstellungstest ist empfehlenswert.

## Ausgabe und Dateiverarbeitung

Quelldateien bleiben unverändert. Die Verarbeitung großer Dateien erfolgt streamend; vollständiges Einlesen einer Logdatei in den Arbeitsspeicher ist nicht vorgesehen. Die Ausgabe wird an einen vom Anwender gewählten Zielort geschrieben.

Die v2.8-Anforderungen verlangen keinen verpflichtenden, zentral konfigurierten Ausgabe-Workspace. Die bestehende Implementierung kann diesen Schutzmechanismus in der Übergangsphase noch erzwingen. Bis die entsprechende Codevereinfachung abgeschlossen und getestet ist, sind die aktuellen Laufzeitbeschränkungen der jeweiligen Programmversion maßgeblich.

## Rollen und Review

Die Benutzer- und Rollenverwaltung bleibt Bestandteil des Produkts. Unterstützt werden die administrativen und fachlichen Aufgaben für Administration, Regelverantwortung, Verarbeitung sowie Review/Freigabe. Rollen können bei geringer Personalstärke einer Person zugeordnet und später auf mehrere Personen verteilt werden.

Ist ein Reviewer/Freigeber zugewiesen, bleibt die bewusste Prüfung und Freigabe Bestandteil des Ablaufs. Ohne zugewiesene Review-Rolle kann der Lauf automatisch freigegeben werden. Rückgabe, Abbruch, Kommentare und nachvollziehbare Statushistorie bleiben erhalten.

## Portable Builds

Die PyInstaller-Spezifikation erstellt ein portables Paket. Windows- und Linux-Pakete werden jeweils auf dem entsprechenden Betriebssystem gebaut. Die CI führt Frontend-Tests, Backend-Tests, Paket-Builds und Smoke-Tests aus. Ein erfolgreicher Smoke-Test ersetzt keinen Integrationstest mit einer konkreten LDAP-/SMTP-Umgebung.
