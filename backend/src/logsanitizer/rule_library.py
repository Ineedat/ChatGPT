"""Curated, conservative starter rules for common application-log data.

Templates are intentionally disabled on insertion. They are starting points,
not a guarantee of complete sensitive-data detection; operators must review
and adapt them to their own log formats before enabling them.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

_LIBRARY: list[dict[str, Any]] = [
    {
        "id": "ipv4-addresses", "name": "IPv4-Adressen", "category": "IP-Adresse",
        "description": "Erkennt syntaktisch gültige IPv4-Adressen (0–255 je Oktett).",
        "pattern": r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\w.])",
        "mapping_prefix": "IP", "priority": 100,
        "example_before": "client=192.0.2.17", "example_after": "client=[IP_1]",
        "notes": "Dokumentationsadressen aus RFC 5737 sind im Beispiel absichtlich synthetisch.",
    },
    {
        "id": "ipv6-addresses", "name": "IPv6-Adressen (Heuristik)", "category": "IP-Adresse",
        "description": "Erkennt typische ausgeschriebene und komprimierte IPv6-Schreibweisen.",
        "pattern": r"(?i)(?<![0-9a-f:])(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}(?![0-9a-f:])|(?<![0-9a-f:])(?:[0-9a-f]{1,4}:){1,7}:(?:[0-9a-f]{1,4})?(?![0-9a-f:])|(?<![0-9a-f:])::(?:[0-9a-f]{1,4}:?){1,7}(?![0-9a-f:])",
        "mapping_prefix": "IP", "priority": 110,
        "example_before": "remote=2001:db8::17", "example_after": "remote=[IP_1]",
        "notes": "Heuristische Erkennung: IPv6-Varianten mit IPv4-Endstück und eingebettete Zonen-IDs separat prüfen.",
    },
    {
        "id": "fqdn-domains", "name": "FQDNs und Domains", "category": "Hostname / Domain",
        "description": "Erkennt mehrteilige DNS-Namen einschließlich Subdomains.",
        "pattern": r"(?i)(?<![a-z0-9_-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(?![a-z0-9_-])",
        "mapping_prefix": "HOST", "priority": 200,
        "example_before": "upstream=api.example.test", "example_after": "upstream=[HOST_1]",
        "notes": "Kann auch öffentliche Domains treffen. Bei Bedarf Quellprofile oder Positiv-/Negativlisten verwenden.",
    },
    {
        "id": "hostname-field", "name": "Hostname-Feldwerte", "category": "Systemname / Infrastruktur",
        "description": "Erkennt Hostnamen direkt hinter hostname=.",
        "pattern": r"(?i)(?<=hostname=)[a-z0-9][a-z0-9._-]{0,252}",
        "mapping_prefix": "HOST", "priority": 210,
        "example_before": "hostname=app-node-01", "example_after": "hostname=[HOST_2]",
        "notes": "Für hostname-Felder; bei abweichenden Feldnamen eine Kopie mit passendem Muster anlegen.",
    },
    {
        "id": "server-field", "name": "Server-Feldwerte", "category": "Systemname / Infrastruktur",
        "description": "Erkennt Servernamen direkt hinter server=.",
        "pattern": r"(?i)(?<=server=)[a-z0-9][a-z0-9._-]{0,252}",
        "mapping_prefix": "SERVER", "priority": 220,
        "example_before": "server=db-prod-02", "example_after": "server=[SERVER_1]",
        "notes": "Nur für das Feld server=; andere Feldnamen können als separate Vorlage ergänzt werden.",
    },
    {
        "id": "email-addresses", "name": "E-Mail-Adressen", "category": "E-Mail-Adresse",
        "description": "Erkennt übliche E-Mail-Adressen in Logtexten.",
        "pattern": r"(?i)(?<![a-z0-9._%+-])[a-z0-9._%+-]{1,64}@[a-z0-9.-]+\.[a-z]{2,63}(?![a-z0-9.-])",
        "mapping_prefix": "EMAIL", "priority": 300,
        "example_before": "user=alex@example.test", "example_after": "user=[EMAIL_1]",
        "notes": "E-Mail-Syntax ist komplex; ungewöhnliche internationale oder quoted Adressen können abweichen.",
    },
    {
        "id": "username-field", "name": "Benutzername-Feld (user=)", "category": "Benutzername",
        "description": "Erkennt Werte direkt hinter user=.",
        "pattern": r"(?i)(?<=user=)[a-z0-9._-]{1,64}",
        "mapping_prefix": "USER", "priority": 310,
        "example_before": "user=alex.muster", "example_after": "user=[USER_1]",
        "notes": "Feldbezogen. Bei username= oder account= eine eigene Kopie ergänzen.",
    },
    {
        "id": "username-long-field", "name": "Benutzername-Feld (username=)", "category": "Benutzername",
        "description": "Erkennt Werte direkt hinter username=.",
        "pattern": r"(?i)(?<=username=)[a-z0-9._-]{1,64}",
        "mapping_prefix": "USER", "priority": 320,
        "example_before": "username=alex.muster", "example_after": "username=[USER_2]",
        "notes": "Feldbezogen; bewusst kein freies Erkennen beliebiger Namen.",
    },
    {
        "id": "phone-numbers", "name": "Telefonnummern (heuristisch)", "category": "Personenbezogene Daten",
        "description": "Erkennt Telefonnummern mit internationalem Präfix oder führender Null.",
        "pattern": r"(?<!\w)(?:\+49|0049|0)[\s./-]?(?:\d[\s./-]?){6,14}\d(?!\w)",
        "mapping_prefix": "PHONE", "priority": 400,
        "example_before": "phone=+49 30 12345678", "example_after": "phone=[PHONE_1]",
        "notes": "Erhöhtes Risiko für Fehlertreffer bei IDs und Messwerten. Vorlage wird deaktiviert hinzugefügt.",
    },
    {
        "id": "birthdate-iso", "name": "Geburtsdatum (birthdate=, ISO)", "category": "Personenbezogene Daten",
        "description": "Erkennt ISO-Datumswerte direkt hinter birthdate=.",
        "pattern": r"(?i)(?<=birthdate=)\d{4}-\d{2}-\d{2}",
        "mapping_prefix": "DATE", "priority": 410,
        "example_before": "birthdate=1980-04-12", "example_after": "birthdate=[DATE_1]",
        "notes": "Prüft das Datumsformat, nicht die Kalendergültigkeit.",
    },
    {
        "id": "birthdate-de", "name": "Geburtsdatum (geburtsdatum=, DE)", "category": "Personenbezogene Daten",
        "description": "Erkennt TT.MM.JJJJ direkt hinter geburtsdatum=.",
        "pattern": r"(?i)(?<=geburtsdatum=)\d{2}\.\d{2}\.\d{4}",
        "mapping_prefix": "DATE", "priority": 420,
        "example_before": "geburtsdatum=12.04.1980", "example_after": "geburtsdatum=[DATE_2]",
        "notes": "Prüft das Datumsformat, nicht die Kalendergültigkeit.",
    },
    {
        "id": "password-field", "name": "Passwort-Feld (password=)", "category": "Passwort / Token / API-Key",
        "description": "Erkennt den Wert direkt hinter password=.",
        "pattern": r"(?i)(?<=password=)[^\s,;\"']{4,}",
        "mapping_prefix": "SECRET", "priority": 500,
        "example_before": "password=synthetic-secret-123", "example_after": "password=[SECRET_1]",
        "notes": "Erfasst nur das benannte Feld; keine allgemeine Erkennung unbekannter Passwörter.",
    },
    {
        "id": "passwd-field", "name": "Passwort-Feld (passwd=)", "category": "Passwort / Token / API-Key",
        "description": "Erkennt den Wert direkt hinter passwd=.",
        "pattern": r"(?i)(?<=passwd=)[^\s,;\"']{4,}",
        "mapping_prefix": "SECRET", "priority": 510,
        "example_before": "passwd=synthetic-secret-123", "example_after": "passwd=[SECRET_2]",
        "notes": "Erfasst nur das benannte Feld.",
    },
    {
        "id": "token-field", "name": "Token-Feld (token=)", "category": "Passwort / Token / API-Key",
        "description": "Erkennt längere Werte direkt hinter token=.",
        "pattern": r"(?i)(?<=token=)[^\s,;\"']{8,}",
        "mapping_prefix": "TOKEN", "priority": 520,
        "example_before": "token=synthetic-token-12345", "example_after": "token=[TOKEN_1]",
        "notes": "Kurze Tokens unter acht Zeichen werden absichtlich nicht erfasst.",
    },
    {
        "id": "api-key-field", "name": "API-Key-Feld (api_key=)", "category": "Passwort / Token / API-Key",
        "description": "Erkennt längere Werte direkt hinter api_key=.",
        "pattern": r"(?i)(?<=api_key=)[^\s,;\"']{8,}",
        "mapping_prefix": "APIKEY", "priority": 530,
        "example_before": "api_key=synthetic-api-key-12345", "example_after": "api_key=[APIKEY_1]",
        "notes": "Bei anderen Schreibweisen wie apiKey= eine eigene Kopie ergänzen.",
    },
    {
        "id": "secret-field", "name": "Secret-Feld (secret=)", "category": "Passwort / Token / API-Key",
        "description": "Erkennt längere Werte direkt hinter secret=.",
        "pattern": r"(?i)(?<=secret=)[^\s,;\"']{4,}",
        "mapping_prefix": "SECRET", "priority": 540,
        "example_before": "secret=synthetic-secret-value", "example_after": "secret=[SECRET_3]",
        "notes": "Feldbezogen; keine vollständige Geheimniserkennung.",
    },
    {
        "id": "bearer-token", "name": "HTTP-Bearer-Token", "category": "Passwort / Token / API-Key",
        "description": "Erkennt Tokenwerte nach dem HTTP-Schema Bearer.",
        "pattern": r"(?i)(?<=bearer )[a-z0-9._~+/-]{12,}={0,2}",
        "mapping_prefix": "TOKEN", "priority": 550,
        "example_before": "Authorization: Bearer syntheticBearerToken123", "example_after": "Authorization: Bearer [TOKEN_2]",
        "notes": "Nur Bearer-Tokenwerte; Basic-Authentifizierung ist nicht enthalten.",
    },
    {
        "id": "windows-paths", "name": "Windows-Dateipfade", "category": "Dateipfad",
        "description": "Erkennt Laufwerkspfade und UNC-Pfade.",
        "pattern": r"(?i)(?<![a-z0-9])(?:[a-z]:\\|\\\\[^\\\s]+\\[^\\\s]+\\)[^\r\n<>|?*\"']+",
        "mapping_prefix": "PATH", "priority": 600,
        "example_before": r"file=C:\Apps\Service\config.yml", "example_after": "file=[PATH_1]",
        "notes": "Kann nachfolgende Satzzeichen miterfassen; bei Bedarf Muster an das Quellformat anpassen.",
    },
    {
        "id": "unix-paths", "name": "Unix-Dateipfade", "category": "Dateipfad",
        "description": "Erkennt absolute Unix-Pfade mit mindestens einem Pfadsegment.",
        "pattern": r"(?<![\w:])/(?:[\w.@+-]+/)*[\w.@+-]+",
        "mapping_prefix": "PATH", "priority": 610,
        "example_before": "config=/opt/app/conf/service.yml", "example_after": "config=[PATH_2]",
        "notes": "Kann URL-Pfade treffen; bei Bedarf auf passende Quellprofile begrenzen.",
    },
    {
        "id": "mac-addresses", "name": "MAC-Adressen", "category": "Systemname / Infrastruktur",
        "description": "Erkennt MAC-Adressen mit Doppelpunkt- oder Bindestrich-Trennern.",
        "pattern": r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])",
        "mapping_prefix": "MAC", "priority": 620,
        "example_before": "mac=02:00:5e:10:00:01", "example_after": "mac=[MAC_1]",
        "notes": "Lokale und global verwaltete MAC-Adressen werden gleich behandelt.",
    },
]

def list_rule_templates() -> list[dict[str, Any]]:
    """Return a defensive copy of the curated starter library."""
    templates = deepcopy(_LIBRARY)
    for template in templates:
        template["match_type"] = "regex"
        template["replacement"] = f"[{template['mapping_prefix']}_1]"
        template["replacement_mode"] = "indexed"
        template["case_sensitive"] = False
        template["enabled"] = False
        template["profile_id"] = None
    return templates


def list_rule_categories() -> list[dict[str, Any]]:
    """Return category metadata and template counts for navigation."""
    templates = list_rule_templates()
    descriptions = {
        "IP-Adresse": "IPv4- und IPv6-Adressen",
        "Hostname / Domain": "FQDNs und Domains",
        "Benutzername": "Benutzer- und Account-Kennungen",
        "E-Mail-Adresse": "E-Mail-Adressen",
        "Personenbezogene Daten": "Telefonnummern und Geburtsdaten",
        "Passwort / Token / API-Key": "Passwörter, Tokens, API-Keys und Bearer-Werte",
        "Dateipfad": "Windows- und Unix-Pfade",
        "Systemname / Infrastruktur": "Hostnamen, Servernamen und MAC-Adressen",
    }
    return [
        {"name": name, "description": description, "template_count": sum(t["category"] == name for t in templates)}
        for name, description in descriptions.items()
    ]
