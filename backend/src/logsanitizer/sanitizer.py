"""Streaming execution for configured text and JSON Lines sanitization rules."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from logsanitizer.rule_config import RuleConfig, SanitizationRule

MAX_LINE_BYTES = 1024 * 1024


class SanitizationError(ValueError):
    """Input cannot be processed safely by the initial streaming engine."""


def _compiled_rule(rule: SanitizationRule) -> re.Pattern[str]:
    pattern = rule.pattern if rule.match_type == "regex" else re.escape(rule.pattern)
    flags = 0 if rule.case_sensitive else re.IGNORECASE
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise SanitizationError("Eine Regel kann nicht kompiliert werden.") from exc


def sanitize_file(
    source_path: Path,
    destination_path: Path,
    config: RuleConfig,
    profile_id: str | None = None,
    format_name: str | None = None,
) -> dict[str, int | str]:
    """Sanitize UTF-8 text/JSONL one bounded line at a time; never modify the source."""
    source = source_path.expanduser()
    destination = destination_path.expanduser()
    if not source.is_absolute() or not destination.is_absolute():
        raise SanitizationError("Quell- und Zieldatei müssen absolute Pfade sein.")
    if source.is_symlink() or not source.is_file():
        raise SanitizationError("Die Quelldatei ist nicht verfügbar oder keine reguläre Datei.")
    if source.resolve() == destination.resolve(strict=False):
        raise SanitizationError("Quell- und Zieldatei dürfen nicht identisch sein.")
    if destination.is_symlink() or destination.exists():
        raise FileExistsError("Die Zieldatei existiert bereits oder ist ein symbolischer Link.")
    if not destination.parent.is_dir():
        raise SanitizationError("Der Zielordner muss bereits existieren.")
    if profile_id is not None and profile_id not in {p.id for p in config.profiles}:
        raise SanitizationError("Das angegebene Quellprofil ist nicht definiert.")

    effective_format = format_name or (
        "jsonl" if source.suffix.casefold() in {".jsonl", ".ndjson"} else "text"
    )
    if effective_format not in {"text", "jsonl"}:
        raise SanitizationError("Unterstützt werden derzeit Textdateien und JSON Lines (UTF-8).")

    rules = [
        rule for rule in config.rules
        if rule.enabled and (rule.profile_id is None or rule.profile_id == profile_id)
    ]
    rules.sort(key=lambda rule: rule.priority)
    compiled = [(rule, _compiled_rule(rule)) for rule in rules]

    processed_bytes = 0
    replacement_count = 0
    line_count = 0
    output_created = False
    try:
        with source.open("rb") as input_stream:
            output_stream = destination.open("xb")
            output_created = True
            with output_stream:
                try:
                    os.chmod(destination, 0o600)
                except OSError:
                    pass
                while True:
                    raw_line = input_stream.readline(MAX_LINE_BYTES + 1)
                    if not raw_line:
                        break
                    if len(raw_line) > MAX_LINE_BYTES:
                        raise SanitizationError(
                            f"Eine Zeile überschreitet das Limit von {MAX_LINE_BYTES} Bytes."
                        )
                    try:
                        line = raw_line.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise SanitizationError(
                            "Die Quelldatei ist nicht vollständig UTF-8-kodiert."
                        ) from exc
                    if effective_format == "jsonl":
                        try:
                            json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise SanitizationError(
                                "Eine Eingabezeile ist kein gültiges JSON."
                            ) from exc
                    for rule, pattern in compiled:
                        line, count = pattern.subn(rule.replacement, line)
                        replacement_count += count
                    if effective_format == "jsonl":
                        try:
                            json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise SanitizationError(
                                "Eine Regel hat eine ungültige JSON-Zeile erzeugt."
                            ) from exc
                    output_stream.write(line.encode("utf-8"))
                    processed_bytes += len(raw_line)
                    line_count += 1
                output_stream.flush()
                os.fsync(output_stream.fileno())
    except Exception:
        if output_created:
            destination.unlink(missing_ok=True)
        raise

    return {
        "status": "completed",
        "input_bytes": processed_bytes,
        "output_bytes": destination.stat().st_size,
        "lines_processed": line_count,
        "replacements": replacement_count,
    }
