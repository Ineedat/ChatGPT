"""Streaming execution for configured text and JSON Lines sanitization rules."""
from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path

import regex as re

from logsanitizer.json_sanitizer import JsonStreamError, sanitize_json_stream, validate_json_stream
from logsanitizer.mapping_store import get_or_create_indexed_mapping
from logsanitizer.rule_config import RuleConfig, SanitizationRule

MAX_LINE_BYTES = 1024 * 1024
REGEX_TIMEOUT_SECONDS = 0.1


class SanitizationError(ValueError):
    """Input cannot be processed safely by the initial streaming engine."""


class SanitizationCancelled(SanitizationError):
    """Raised when a caller requests cancellation of an active sanitization run."""


ProgressCallback = Callable[[dict[str, int | str]], None]
CancelCheck = Callable[[], bool]


def _check_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise SanitizationCancelled("Bereinigung wurde abgebrochen.")


def _compiled_rule(rule: SanitizationRule) -> re.Pattern[str]:
    pattern = rule.pattern if rule.match_type == "regex" else re.escape(rule.pattern)
    flags = 0 if rule.case_sensitive else re.IGNORECASE
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise SanitizationError("Eine Regel kann nicht kompiliert werden.") from exc



def _validate_sanitized_output(
    path: Path,
    compiled: list[tuple[SanitizationRule, re.Pattern[str]]],
    format_name: str,
    cancel_check: CancelCheck | None = None,
    progress_callback: ProgressCallback | None = None,
    total_bytes: int = 0,
    initial_bytes: int = 0,
) -> int:
    """Re-read output in bounded lines and reject syntax errors or configured residuals."""
    with path.open("rb") as output_stream:
        line_number = 0
        while True:
            raw_line = output_stream.readline(MAX_LINE_BYTES + 1)
            if not raw_line:
                break
            _check_cancelled(cancel_check)
            line_number += 1
            if len(raw_line) > MAX_LINE_BYTES:
                raise SanitizationError(
                    f"Die Ausgabe überschreitet in Zeile {line_number} das Limit von {MAX_LINE_BYTES} Bytes."
                )
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise SanitizationError("Die Ausgabe ist nicht vollständig UTF-8-kodiert.") from exc
            if format_name == "jsonl":
                try:
                    json.loads(line)
                except (json.JSONDecodeError, ValueError) as exc:
                    raise SanitizationError(
                        f"Die Ausgabe enthält ungültiges JSON in Zeile {line_number}."
                    ) from exc
            if progress_callback is not None:
                progress_callback({
                    "phase": "validating",
                    "processed_bytes": initial_bytes + output_stream.tell(),
                    "total_bytes": total_bytes,
                    "lines_processed": line_number,
                })
            for rule, pattern in compiled:
                try:
                    matched = pattern.search(line, timeout=REGEX_TIMEOUT_SECONDS)
                except TimeoutError as exc:
                    raise SanitizationError(
                        "Die Restmusterprüfung hat das Zeitlimit überschritten."
                    ) from exc
                if matched:
                    raise SanitizationError(
                        f"Restmusterprüfung fehlgeschlagen: Regel '{rule.id}' trifft in Ausgabezeile {line_number}."
                    )
    return 0


def sanitize_file(
    source_path: Path,
    destination_path: Path,
    config: RuleConfig,
    profile_id: str | None = None,
    format_name: str | None = None,
    project_id: str | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
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
    if effective_format not in {"text", "jsonl", "json"}:
        raise SanitizationError("Unterstützt werden derzeit Text, JSON und JSON Lines (UTF-8).")

    rules = [
        rule for rule in config.rules
        if rule.enabled and (rule.profile_id is None or rule.profile_id == profile_id)
    ]
    rules.sort(key=lambda rule: rule.priority)
    compiled = [(rule, _compiled_rule(rule)) for rule in rules]
    if project_id is None and any(rule.replacement_mode == "indexed" for rule in rules):
        raise SanitizationError("Indexierte Ersetzungen benötigen eine Projekt-ID.")

    total_bytes = source.stat().st_size
    processed_bytes = 0
    replacement_count = 0
    line_count = 0
    staging = destination.with_name(f".{destination.name}.logsanitizer-{uuid.uuid4().hex}.tmp")
    staging_created = False
    if effective_format == "json":
        try:
            try:
                with (
                    source.open("r", encoding="utf-8-sig", newline="") as input_stream,
                    staging.open("x", encoding="utf-8", newline="") as output_stream,
                ):
                    staging_created = True
                    try:
                        os.chmod(staging, 0o600)
                    except OSError:
                        pass
                    replacement_count, line_count = sanitize_json_stream(
                        input_stream, output_stream, compiled, project_id,
                        cancel_check, progress_callback, total_bytes,
                    )
                    output_stream.flush()
                    os.fsync(output_stream.fileno())
                _check_cancelled(cancel_check)
                with staging.open("r", encoding="utf-8", newline="") as validation_stream:
                    validate_json_stream(validation_stream, compiled, cancel_check)
                _check_cancelled(cancel_check)
            except JsonStreamError as exc:
                if cancel_check is not None and cancel_check():
                    raise SanitizationCancelled("Bereinigung wurde abgebrochen.") from exc
                raise SanitizationError(str(exc)) from exc
            if destination.exists() or destination.is_symlink():
                raise FileExistsError("Die Zieldatei existiert bereits oder ist ein symbolischer Link.")
            os.link(staging, destination)
            staging.unlink()
            staging_created = False
        except Exception:
            if staging_created:
                staging.unlink(missing_ok=True)
            raise
        return {
            "status": "completed",
            "input_bytes": total_bytes,
            "output_bytes": destination.stat().st_size,
            "lines_processed": line_count,
            "replacements": replacement_count,
            "validated": True,
            "residual_matches": 0,
            "validation_scope": "configured_rules_and_json_structure",
        }

    try:
        with source.open("rb") as input_stream:
            _check_cancelled(cancel_check)
            output_stream = staging.open("xb")
            staging_created = True
            with output_stream:
                try:
                    os.chmod(staging, 0o600)
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
                        try:
                            if rule.replacement_mode == "indexed":
                                assert project_id is not None
                                prefix = rule.mapping_prefix or rule.category
                                line, count = pattern.subn(
                                    lambda match, project_id=project_id, category=rule.category, prefix=prefix: (
                                        get_or_create_indexed_mapping(
                                            project_id, category, prefix, match.group(0)
                                        )
                                    ),
                                    line,
                                    timeout=REGEX_TIMEOUT_SECONDS,
                                )
                            else:
                                line, count = pattern.subn(
                                    rule.replacement, line, timeout=REGEX_TIMEOUT_SECONDS
                                )
                        except TimeoutError as exc:
                            raise SanitizationError(
                                "Die Regelausführung hat das Zeitlimit überschritten."
                            ) from exc
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
                    if progress_callback is not None:
                        progress_callback({
                            "phase": "sanitizing",
                            "processed_bytes": processed_bytes,
                            "total_bytes": total_bytes,
                            "lines_processed": line_count,
                        })
                output_stream.flush()
                os.fsync(output_stream.fileno())
        _check_cancelled(cancel_check)
        residual_matches = _validate_sanitized_output(
            staging, compiled, effective_format, cancel_check, progress_callback,
            staging.stat().st_size, 0,
        )
        _check_cancelled(cancel_check)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("Die Zieldatei existiert bereits oder ist ein symbolischer Link.")
        os.link(staging, destination)
        staging.unlink()
        staging_created = False
    except Exception:
        if staging_created:
            staging.unlink(missing_ok=True)
        raise

    return {
        "status": "completed",
        "input_bytes": processed_bytes,
        "output_bytes": destination.stat().st_size,
        "lines_processed": line_count,
        "replacements": replacement_count,
        "validated": True,
        "residual_matches": residual_matches,
        "validation_scope": "configured_rules_and_format",
    }
