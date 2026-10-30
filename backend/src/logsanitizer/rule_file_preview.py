"""Bounded, read-only source-file windows for the rule preview."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from logsanitizer.rule_config import RuleConfig
from logsanitizer.rule_preview import MAX_PREVIEW_CHARS, RulePreviewError, preview_rules

MAX_PREVIEW_BYTES = MAX_PREVIEW_CHARS * 4


def preview_file_window(
    source: Path,
    config: RuleConfig,
    *,
    byte_offset: int = 0,
    from_end: bool = False,
    profile_id: str | None = None,
    rule_id: str | None = None,
) -> dict[str, Any]:
    """Read and simulate one bounded UTF-8 text window without writing anything."""
    if source.is_symlink() or not source.is_file():
        raise RulePreviewError("Die registrierte Quelldatei ist nicht verfügbar.")
    before = source.stat()
    size = before.st_size
    if from_end:
        byte_offset = max(0, size - MAX_PREVIEW_BYTES)
    byte_offset = max(0, min(int(byte_offset), size))

    with source.open("rb") as stream:
        stream.seek(byte_offset)
        if byte_offset:
            stream.seek(byte_offset - 1)
            previous_byte = stream.read(1)
            stream.seek(byte_offset)
            if previous_byte != b"\\n":
                stream.readline(1024 * 1024 + 1)
        start_offset = stream.tell()
        raw = stream.read(MAX_PREVIEW_BYTES)
        while True:
            try:
                decoded = raw.decode("utf-8-sig" if start_offset == 0 else "utf-8")
                break
            except UnicodeDecodeError as exc:
                if exc.reason == "unexpected end of data" and exc.end == len(raw):
                    raw = raw[:exc.start]
                    continue
                raise RulePreviewError("Die Vorschau unterstützt ausschließlich gültige UTF-8-Logdateien.") from exc

        if len(decoded) > MAX_PREVIEW_CHARS:
            decoded = decoded[:MAX_PREVIEW_CHARS]
            raw = decoded.encode("utf-8")
        if stream.tell() < size and decoded and not decoded.endswith(("\n", "\r")):
            last_newline = max(decoded.rfind("\n"), decoded.rfind("\r"))
            if last_newline < 0:
                raise RulePreviewError("Eine einzelne Logzeile überschreitet die maximale Vorschaufenstergröße.")
            decoded = decoded[: last_newline + 1]
            raw = decoded.encode("utf-8")
        next_offset = start_offset + len(raw)

    after = source.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise RulePreviewError("Die Quelldatei wurde während der Vorschau verändert. Bitte erneut laden.")
    if not decoded:
        raise RulePreviewError("An dieser Position wurde kein vollständiger UTF-8-Textabschnitt gefunden.")

    result = preview_rules(decoded, config, profile_id, rule_id)
    return {
        **result,
        "original_text": decoded,
        "source_offset": start_offset,
        "next_offset": next_offset,
        "total_bytes": size,
        "has_previous": start_offset > 0,
        "has_next": next_offset < size,
        "window_chars": len(decoded),
    }
