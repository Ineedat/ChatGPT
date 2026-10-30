"""Non-persistent rule testing and sanitization preview for synthetic samples."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import regex as re

from logsanitizer.rule_config import RuleConfig, SanitizationRule

MAX_PREVIEW_CHARS = 65_536
MAX_REPORTED_MATCHES = 100
REGEX_TIMEOUT_SECONDS = 0.1


class RulePreviewError(ValueError):
    """The requested preview cannot be evaluated safely."""


def _compile(rule: SanitizationRule) -> re.Pattern[str]:
    source = rule.pattern if rule.match_type == "regex" else re.escape(rule.pattern)
    try:
        return re.compile(source, 0 if rule.case_sensitive else re.IGNORECASE)
    except re.error as exc:
        raise RulePreviewError(f"Regel '{rule.id}' enthält ein ungültiges Muster.") from exc


def preview_rules(
    sample_text: str,
    config: RuleConfig,
    profile_id: str | None = None,
    rule_id: str | None = None,
) -> dict[str, Any]:
    """Simulate rules in memory; never reads files or writes project mappings."""
    if len(sample_text) > MAX_PREVIEW_CHARS:
        raise RulePreviewError(f"Die Testeingabe ist auf {MAX_PREVIEW_CHARS} Zeichen begrenzt.")
    if profile_id is not None and profile_id not in {profile.id for profile in config.profiles}:
        raise RulePreviewError("Das ausgewählte Quellprofil ist nicht definiert.")

    if rule_id is not None:
        selected = next((rule for rule in config.rules if rule.id == rule_id), None)
        if selected is None:
            raise RulePreviewError("Die ausgewählte Regel ist nicht vorhanden.")
        if selected.profile_id is not None and selected.profile_id != profile_id:
            raise RulePreviewError("Die ausgewählte Regel gehört zu einem anderen Quellprofil.")
        rules = [selected]  # A single-rule test also works for disabled draft rules.
    else:
        rules = [
            rule for rule in config.rules
            if rule.enabled and (rule.profile_id is None or rule.profile_id == profile_id)
        ]
    rules.sort(key=lambda item: item.priority)
    compiled = [(rule, _compile(rule)) for rule in rules]

    initial_matches: dict[str, list[dict[str, Any]]] = {}
    for rule, pattern in compiled:
        try:
            initial_matches[rule.id] = [
                {"start": match.start(), "end": match.end(), "value": match.group(0)}
                for index, match in enumerate(pattern.finditer(sample_text, timeout=REGEX_TIMEOUT_SECONDS))
                if index < MAX_REPORTED_MATCHES
            ]
        except TimeoutError as exc:
            raise RulePreviewError(f"Das Muster von Regel '{rule.id}' überschreitet das Zeitlimit.") from exc

    overlaps: list[dict[str, Any]] = []
    if rule_id is None:
        for first_index, (first_rule, _) in enumerate(compiled):
            for second_rule, _ in compiled[first_index + 1:]:
                for first in initial_matches[first_rule.id]:
                    for second in initial_matches[second_rule.id]:
                        if first["start"] < second["end"] and second["start"] < first["end"]:
                            overlaps.append({
                                "first_rule_id": first_rule.id,
                                "second_rule_id": second_rule.id,
                                "start": max(first["start"], second["start"]),
                                "end": min(first["end"], second["end"]),
                                "example": sample_text[max(first["start"], second["start"]):min(first["end"], second["end"])],
                            })
                            if len(overlaps) >= MAX_REPORTED_MATCHES:
                                break
                    if len(overlaps) >= MAX_REPORTED_MATCHES:
                        break
                if len(overlaps) >= MAX_REPORTED_MATCHES:
                    break

    current = sample_text
    counters: dict[tuple[str, str], int] = defaultdict(int)
    indexed_values: dict[tuple[str, str, str], str] = {}
    generated_fragments: list[tuple[str, str]] = []
    results: list[dict[str, Any]] = []

    for rule, pattern in compiled:
        try:
            found = list(pattern.finditer(current, timeout=REGEX_TIMEOUT_SECONDS))
            match_details: list[dict[str, Any]] = []

            def replacement_for(match: re.Match) -> str:
                value = match.group(0)
                if rule.replacement_mode == "indexed":
                    prefix = rule.mapping_prefix or "VALUE"
                    key = (rule.category, prefix, value)
                    if key not in indexed_values:
                        counter_key = (rule.category, prefix)
                        counters[counter_key] += 1
                        indexed_values[key] = f"[{prefix}_{counters[counter_key]}]"
                    replacement = indexed_values[key]
                else:
                    try:
                        replacement = match.expand(rule.replacement)
                    except re.error as exc:
                        raise RulePreviewError(
                            f"Ersetzungswert von Regel '{rule.id}' ist ungültig."
                        ) from exc
                chained_from = [
                    source_id for source_id, fragment in generated_fragments
                    if fragment and value in fragment
                ]
                if len(match_details) < MAX_REPORTED_MATCHES:
                    match_details.append({
                        "start": match.start(),
                        "end": match.end(),
                        "value": value,
                        "replacement": replacement,
                        "chained_from": list(dict.fromkeys(chained_from)),
                    })
                generated_fragments.append((rule.id, replacement))
                return replacement

            current, count = pattern.subn(replacement_for, current, timeout=REGEX_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise RulePreviewError(f"Das Muster von Regel '{rule.id}' überschreitet das Zeitlimit.") from exc
        results.append({
            "rule_id": rule.id,
            "name": rule.name,
            "priority": rule.priority,
            "enabled": rule.enabled,
            "match_count": count,
            "matches": match_details,
            "matches_truncated": count > MAX_REPORTED_MATCHES,
            "chained_match_count": sum(bool(item["chained_from"]) for item in match_details),
        })

    return {
        "mode": "single-rule" if rule_id is not None else "enabled-rules",
        "profile_id": profile_id,
        "input_chars": len(sample_text),
        "output_chars": len(current),
        "preview_text": current,
        "changed": current != sample_text,
        "rule_results": results,
        "overlaps": overlaps,
        "overlaps_truncated": len(overlaps) >= MAX_REPORTED_MATCHES,
    }
