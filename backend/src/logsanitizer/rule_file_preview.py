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
            if previous_byte != b"\n":
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

        if from_end and len(decoded) > MAX_PREVIEW_CHARS:
            removed = decoded[:-MAX_PREVIEW_CHARS]
            start_offset += len(removed.encode("utf-8"))
            decoded = decoded[-MAX_PREVIEW_CHARS:]
            first_newline = max(decoded.find("\n"), decoded.find("\r"))
            if first_newline >= 0:
                removed_prefix = decoded[: first_newline + 1]
                start_offset += len(removed_prefix.encode("utf-8"))
                decoded = decoded[first_newline + 1:]
        else:
            was_truncated = len(decoded) > MAX_PREVIEW_CHARS
            read_to_eof = stream.tell() >= size
            if was_truncated:
                decoded = decoded[:MAX_PREVIEW_CHARS]
            if (not read_to_eof or was_truncated) and decoded and not decoded.endswith(("\\n", "\\r")):
                last_newline = max(decoded.rfind("\\n"), decoded.rfind("\\r"))
                if last_newline < 0:
                    raise RulePreviewError("Eine einzelne Logzeile überschreitet die maximale Vorschaufenstergröße.")
                decoded = decoded[: last_newline + 1]
        next_offset = start_offset + len(decoded.encode("utf-8"))

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
