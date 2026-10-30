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

Im Netzwerkprofil erfolgt die Anmeldung über LDAP/Active Directory; lokale Passwort-Fallback-Anmeldung ist deaktiviert. LDAP wird mit LDAPS oder StartTLS betrieben. Zu konfigurieren sind Host/Port, Bind-DN, User-Search-Base, Benutzerfilter, Gruppenattribut und explizite Gruppenzuordnung zu den Rollen admin, rule_owner, operator, reviewer und approver. Das Dienstkonto-Geheimnis wird ausschließlich über die lokale Prozessumgebung bereitgestellt. Optional kann eine CA-Datei angegeben werden.

SMTP kann für Benachrichtigungen über ausstehende Reviews und Rückgaben aktiviert werden. Host, Port, Sicherheitsmodus (STARTTLS oder SSL), Absender und Empfängerlisten werden über die Deployment-Konfiguration festgelegt. Zugangsdaten werden ausschließlich über lokale Umgebungsvariablen bereitgestellt und niemals in die JSON-Datei oder das portable Paket geschrieben. SMTP-Ausfälle dürfen die Verarbeitung nicht blockieren.

Vor dem Start im Netzwerkprofil müssen echte LDAP-/SMTP-Endpunkte und Zertifikate aus der Zielumgebung eingetragen werden. Der Netzwerkzugriff bleibt auf das definierte Air-Gap-Netz begrenzt.

TLS kann entsprechend der konkreten Netzwerkinfrastruktur eingesetzt werden. Es ist kein Produktziel, für einen vollständig isolierten, kontrollierten Air-Gap-Betrieb eine komplexe Zertifikats- und Geheimnisverwaltung zwingend vorauszusetzen. Die Netzfreigabe und die konkrete Transportabsicherung müssen zur jeweiligen Umgebung passen.

## Daten, Mapping und Backups

Projekte, importierte Dateimetadaten, Review-Informationen und Mapping-Zuordnungen werden lokal in SQLite gespeichert. Die Mapping-Zuordnungen sind projektbezogen: derselbe Originalwert erhält innerhalb eines Projekts über mehrere Dateien hinweg denselben Ersatzwert.

Mapping-Zuordnungen werden direkt in der lokalen SQLite-Datenbank gespeichert. Eine separate Schlüsseldatei und eine Migration verschlüsselter Altbestände sind nicht Bestandteil der finalen Produktversion. Da vor dem finalen Einsatz keine echten Logs verarbeitet werden, beginnt die Produktivnutzung mit einer frisch angelegten Mapping-Datenbank. Eine vorhandene Mapping-Datenbank aus Entwicklungs- oder Testständen wird nicht übernommen.

Vor regulären Updates ist eine Sicherung des gesamten Datenverzeichnisses empfehlenswert. Ein Wiederherstellungstest stellt sicher, dass Projekte, Mapping-Zuordnungen und Review-Historie verfügbar bleiben.

## Ausgabe und Dateiverarbeitung

Quelldateien bleiben unverändert. Die Verarbeitung großer Dateien erfolgt streamend; vollständiges Einlesen einer Logdatei in den Arbeitsspeicher ist nicht vorgesehen. Die Ausgabe wird an einen vom Anwender gewählten Zielort geschrieben.

Der Anwender kann einen absoluten Ausgabepfad frei wählen. Der Zielordner muss bereits existieren; vorhandene Zieldateien werden nicht überschrieben. Eine Workspace-Allowlist oder ein zentral konfigurierter Ausgabeordner ist nicht erforderlich.

## Rollen und Review

Die Benutzer- und Rollenverwaltung bleibt Bestandteil des Produkts. Unterstützt werden die administrativen und fachlichen Aufgaben für Administration, Regelverantwortung, Verarbeitung sowie Review/Freigabe. Rollen können bei geringer Personalstärke einer Person zugeordnet und später auf mehrere Personen verteilt werden.

Ist ein Reviewer/Freigeber zugewiesen, bleibt die bewusste Prüfung und Freigabe Bestandteil des Ablaufs. Ohne zugewiesene Review-Rolle kann der Lauf automatisch freigegeben werden. Rückgabe, Abbruch, Kommentare und nachvollziehbare Statushistorie bleiben erhalten.

## Portable Builds

Die PyInstaller-Spezifikation erstellt ein portables Paket mit lokalem Frontend, Offline-Hilfe, Dokumentation und Beispielkonfiguration. Windows- und Linux-Pakete werden jeweils auf dem entsprechenden Betriebssystem gebaut. Die CI führt Frontend-Tests, Backend-Tests, Paket-Builds und Standalone-Smoke-Tests aus. Ein erfolgreicher Standalone-Smoke-Test beweist nicht die LDAP-/SMTP-Erreichbarkeit. Vor Freigabe sind mindestens erfolgreiche LDAP-Anmeldungen für die relevanten Rollen, ein abgewiesener Benutzer ohne passende Gruppe, Zertifikatsprüfung sowie SMTP-Zustellung für Review und Rückgabe im echten Air-Gap-Netz zu protokollieren.


## Automatisierte Netzwerkprofil-Prüfung

Die CI startet das portable Paket zusätzlich einmal mit dem Netzwerkprofil, einem zur Laufzeit erzeugten lokalen TLS-Zertifikat sowie synthetischer LDAP- und SMTP-Konfiguration. Damit werden PyInstaller-Start, Konfigurationsprüfung und HTTPS-Erreichbarkeit des Netzwerkprofils auf Windows und Linux abgedeckt.

Dieser Smoke-Test verbindet sich absichtlich nicht mit einem echten LDAP- oder SMTP-Server. Vor der Inbetriebnahme im Air-Gap-Netz sind deshalb echte LDAP-Anmeldung, Gruppenzuordnung, Zertifikatskette und SMTP-Zustellung gemäß der obigen Abnahmeliste zu testen.
