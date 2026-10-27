"""Streaming format validation for local source files.

Validation reports classifications and safe error locations only; it never returns
source content. The JSON parser validates syntax incrementally without retaining
the complete document in memory.
"""
from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TextIO

CHUNK_SIZE = 64 * 1024
MAX_JSON_DEPTH = 128
FORMATS = {"text", "json", "jsonl", "xml", "csv"}


class FormatValidationError(ValueError):
    """A source file does not conform to its selected format."""


class _JsonStreamParser:
    def __init__(self, source: TextIO) -> None:
        self.source = source
        self.buffer = ""
        self.position = 0
        self.eof = False

    def _fill(self) -> bool:
        if self.position < len(self.buffer):
            return True
        self.buffer = self.source.read(CHUNK_SIZE)
        self.position = 0
        if not self.buffer:
            self.eof = True
            return False
        return True

    def peek(self) -> str:
        return self.buffer[self.position] if self._fill() else ""

    def take(self) -> str:
        char = self.peek()
        if char:
            self.position += 1
        return char

    def whitespace(self) -> None:
        while self.peek() in (" ", "\t", "\r", "\n") and self.peek():
            self.take()

    def expect(self, expected: str) -> None:
        if self.take() != expected:
            raise FormatValidationError("Ungültige JSON-Syntax.")

    def string(self) -> None:
        self.expect('"')
        while True:
            char = self.take()
            if not char:
                raise FormatValidationError("Nicht abgeschlossener JSON-String.")
            if char == '"':
                return
            if ord(char) < 0x20:
                raise FormatValidationError("Steuerzeichen in JSON-String.")
            if char == "\\":
                escape = self.take()
                if escape in '"\\/bfnrt':
                    continue
                if escape != "u":
                    raise FormatValidationError("Ungültige Escape-Sequenz in JSON.")
                for _ in range(4):
                    if self.take() not in "0123456789abcdefABCDEF":
                        raise FormatValidationError("Ungültige Unicode-Escape-Sequenz in JSON.")

    def number(self) -> None:
        token = ""
        while self.peek() and self.peek() in "-+0123456789.eE":
            token += self.take()
        if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", token):
            raise FormatValidationError("Ungültige JSON-Zahl.")

    def literal(self, value: str) -> None:
        for char in value:
            self.expect(char)

    def value(self, depth: int = 0) -> None:
        if depth > MAX_JSON_DEPTH:
            raise FormatValidationError("JSON-Verschachtelung überschreitet das Limit.")
        self.whitespace()
        char = self.peek()
        if char == '"':
            self.string()
        elif char == "{":
            self.take()
            self.whitespace()
            if self.peek() == "}":
                self.take()
                return
            while True:
                self.whitespace()
                if self.peek() != '"':
                    raise FormatValidationError("JSON-Objektschlüssel fehlt.")
                self.string()
                self.whitespace()
                self.expect(":")
                self.value(depth + 1)
                self.whitespace()
                char = self.take()
                if char == "}":
                    return
                if char != ",":
                    raise FormatValidationError("Ungültiges JSON-Objekt.")
        elif char == "[":
            self.take()
            self.whitespace()
            if self.peek() == "]":
                self.take()
                return
            while True:
                self.value(depth + 1)
                self.whitespace()
                char = self.take()
                if char == "]":
                    return
                if char != ",":
                    raise FormatValidationError("Ungültiges JSON-Array.")
        elif char == "t":
            self.literal("true")
        elif char == "f":
            self.literal("false")
        elif char == "n":
            self.literal("null")
        elif char == "-" or char.isdigit():
            self.number()
        else:
            raise FormatValidationError("Ungültiger JSON-Wert.")

    def validate(self) -> None:
        self.whitespace()
        if not self.peek():
            raise FormatValidationError("JSON-Datei ist leer.")
        self.value()
        self.whitespace()
        if self.peek():
            raise FormatValidationError("Unerwartete Daten nach dem JSON-Wert.")


def validate_file(path: Path, format_name: str) -> dict[str, str | int | bool]:
    """Validate a complete file with streaming reads and safe, generic errors."""
    if format_name not in FORMATS:
        return {
            "valid": False,
            "format": format_name,
            "bytes_checked": 0,
            "error": "Format unbekannt oder nicht unterstützt; bitte explizit auswählen.",
        }
    bytes_checked = path.stat().st_size
    try:
        if format_name == "json":
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                _JsonStreamParser(source).validate()
        elif format_name == "jsonl":
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                found = False
                for line_number, line in enumerate(source, 1):
                    if not line.strip():
                        continue
                    found = True
                    try:
                        json.loads(line)
                    except (json.JSONDecodeError, ValueError) as exc:
                        raise FormatValidationError(
                            f"Ungültiges JSONL in Zeile {line_number}."
                        ) from exc
                if not found:
                    raise FormatValidationError("JSONL-Datei enthält keine JSON-Werte.")
        elif format_name == "text":
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                while source.read(CHUNK_SIZE):
                    pass
        elif format_name == "csv":
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                reader = csv.reader(source, strict=True)
                for _row in reader:
                    pass
        elif format_name == "xml":
            with path.open("rb") as source:
                for _event, element in ET.iterparse(source, events=("end",)):
                    element.clear()
    except FormatValidationError as exc:
        return {"valid": False, "format": format_name, "bytes_checked": bytes_checked, "error": str(exc)}
    except (UnicodeError, csv.Error, ET.ParseError, json.JSONDecodeError, OSError) as exc:
        message = "Datei ist nicht gültig für das ausgewählte Format."
        if isinstance(exc, ET.ParseError):
            message = "Ungültige XML-Struktur."
        elif isinstance(exc, csv.Error):
            message = "Ungültige CSV-Struktur."
        elif isinstance(exc, UnicodeError):
            message = "Datei ist kein gültiger UTF-8-Text."
        elif isinstance(exc, OSError):
            message = "Quelldatei konnte nicht vollständig gelesen werden."
        return {"valid": False, "format": format_name, "bytes_checked": bytes_checked, "error": message}
    return {"valid": True, "format": format_name, "bytes_checked": bytes_checked, "error": ""}
