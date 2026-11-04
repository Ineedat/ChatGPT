from logsanitizer.rule_config import RuleConfig
from logsanitizer.rule_library import list_rule_categories, list_rule_templates


def test_starter_library_covers_required_categories_and_templates_validate() -> None:
    templates = list_rule_templates()
    categories = {item["name"] for item in list_rule_categories()}
    required = {
        "IP-Adresse", "Hostname / Domain", "Benutzername", "E-Mail-Adresse",
        "Personenbezogene Daten", "Passwort / Token / API-Key", "Dateipfad",
        "Systemname / Infrastruktur",
    }
    assert required <= categories
    assert len(templates) >= 15
    config = RuleConfig.model_validate({"schema_version": 1, "profiles": [], "rules": [
        {key: value for key, value in item.items() if key in {
            "id", "name", "category", "match_type", "pattern", "replacement",
            "replacement_mode", "mapping_prefix", "case_sensitive", "priority",
            "profile_id", "enabled",
        }}
        for item in templates
    ]})
    assert len(config.rules) == len(templates)
    assert all(not rule.enabled for rule in config.rules)


def test_starter_templates_are_individually_editable_and_defensive_copies() -> None:
    first = list_rule_templates()
    first[0]["name"] = "mutated"
    second = list_rule_templates()
    assert second[0]["name"] == "IPv4-Adressen"
    assert all(item["replacement_mode"] == "indexed" for item in second)
    assert all(item["profile_id"] is None for item in second)


def test_ipv4_template_matches_documentation_address_only() -> None:
    import regex

    template = next(item for item in list_rule_templates() if item["id"] == "ipv4-addresses")
    pattern = regex.compile(template["pattern"], regex.IGNORECASE)
    assert pattern.search("client=192.0.2.17")
    assert not pattern.search("client=999.0.2.17")


def test_every_starter_template_matches_its_synthetic_example() -> None:
    import regex

    for template in list_rule_templates():
        pattern = regex.compile(template["pattern"], regex.IGNORECASE)
        assert pattern.search(template["example_before"]), template["id"]
