"""Bounded-memory JSON document sanitization.

The parser rewrites JSON string tokens as they stream through the file. It does
not materialize the complete document and preserves all non-string tokens and
whitespace. Rule matching is performed on decoded JSON strings (keys and values).
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import TextIO

from logsanitizer.mapping_store import get_or_create_indexed_mapping
from logsanitizer.rule_config import SanitizationRule

CHUNK_SIZE = 64 * 1024
MAX_STRING_CHARS = 1024 * 1024
MAX_DEPTH = 128
TIMEOUT_SECONDS = 0.1
CancelCheck = Callable[[], bool]
ProgressCallback = Callable[[dict[str, int | str]], None]


class JsonStreamError(ValueError):
    """A JSON document is invalid or contains a residual configured match."""


class _Parser:
    def __init__(
        self,
        source: TextIO,
        destination: TextIO | None,
        rules: list[tuple[SanitizationRule, re.Pattern[str]]],
        project_id: str | None,
        transform: bool,
        cancel_check: CancelCheck | None,
        progress_callback: ProgressCallback | None,
        total_bytes: int,
    ) -> None:
        self.source = source
        self.destination = destination
        self.rules = rules
        self.project_id = project_id
        self.transform = transform
        self.cancel_check = cancel_check
        self.progress_callback = progress_callback
        self.total_bytes = total_bytes
        self.buffer = ""
        self.position = 0
        self.eof = False
        self.replacements = 0
        self.lines = 0
        self.last_progress = 0

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
            if char == "\n":
                self.lines += 1
        return char

    def write(self, value: str) -> None:
        if self.destination is not None:
            self.destination.write(value)

    def check_cancel(self) -> None:
        if self.cancel_check is not None and self.cancel_check():
            raise JsonStreamError("Bereinigung wurde abgebrochen.")

    def report(self) -> None:
        if self.progress_callback is None:
            return
        try:
            position = self.source.tell()
        except (OSError, ValueError):
            position = 0
        if position - self.last_progress >= CHUNK_SIZE or not self.peek():
            self.last_progress = position
            self.progress_callback({
                "phase": "sanitizing" if self.transform else "validating",
                "processed_bytes": min(position, self.total_bytes),
                "total_bytes": self.total_bytes,
                "lines_processed": self.lines,
            })

    def whitespace(self) -> None:
        while self.peek() in (" ", "\t", "\r", "\n") and self.peek():
            self.write(self.take())

    def expect(self, expected: str) -> None:
        if self.take() != expected:
            raise JsonStreamError("Ungültige JSON-Syntax.")

    def string(self) -> None:
        raw = ['"']
        self.expect('"')
        escaped = False
        while True:
            self.check_cancel()
            char = self.take()
            if not char:
                raise JsonStreamError("Nicht abgeschlossener JSON-String.")
            raw.append(char)
            if len(raw) > MAX_STRING_CHARS:
                raise JsonStreamError(
                    f"Ein JSON-String überschreitet das Limit von {MAX_STRING_CHARS} Zeichen."
                )
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                break
            elif ord(char) < 0x20:
                raise JsonStreamError("Steuerzeichen in JSON-String.")
        try:
            value = json.loads("".join(raw))
        except json.JSONDecodeError as exc:
            raise JsonStreamError("Ungültiger JSON-String.") from exc
        if self.transform:
            for rule, pattern in self.rules:
                try:
                    if rule.replacement_mode == "indexed":
                        if self.project_id is None:
                            raise JsonStreamError("Indexierte Ersetzungen benötigen eine Projekt-ID.")
                        prefix = rule.mapping_prefix or rule.category
                        value, count = pattern.subn(
                            lambda match, project=self.project_id, category=rule.category, p=prefix: (
                                get_or_create_indexed_mapping(project, category, p, match.group(0))
                            ),
                            value,
                            timeout=TIMEOUT_SECONDS,
                        )
                    else:
                        value, count = pattern.subn(
                            rule.replacement, value, timeout=TIMEOUT_SECONDS
                        )
                except TimeoutError as exc:
                    raise JsonStreamError("Die Regelausführung hat das Zeitlimit überschritten.") from exc
                self.replacements += count
            self.write(json.dumps(value, ensure_ascii=False))
        else:
            for rule, pattern in self.rules:
                try:
                    if pattern.search(value, timeout=TIMEOUT_SECONDS):
                        raise JsonStreamError(
                            f"Restmusterprüfung fehlgeschlagen: Regel '{rule.id}' trifft in JSON-String."
                        )
                except TimeoutError as exc:
                    raise JsonStreamError("Die Restmusterprüfung hat das Zeitlimit überschritten.") from exc
            self.write("".join(raw))

    def number(self) -> None:
        token = ""
        while self.peek() and self.peek() in "-+0123456789.eE":
            token += self.take()
        if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", token):
            raise JsonStreamError("Ungültige JSON-Zahl.")
        self.write(token)

    def literal(self, value: str) -> None:
        for char in value:
            self.expect(char)
        self.write(value)

    def value(self, depth: int = 0) -> None:
        self.check_cancel()
        if depth > MAX_DEPTH:
            raise JsonStreamError("JSON-Verschachtelung überschreitet das Limit.")
        self.whitespace()
        char = self.peek()
        if char == '"':
            self.string()
        elif char == "{":
            self.write(self.take())
            self.whitespace()
            if self.peek() == "}":
                self.write(self.take())
                return
            while True:
                self.whitespace()
                if self.peek() != '"':
                    raise JsonStreamError("JSON-Objektschlüssel fehlt.")
                self.string()
                self.whitespace()
                self.expect(":")
                self.write(":")
                self.value(depth + 1)
                self.whitespace()
                char = self.take()
                if char == "}":
                    self.write(char)
                    return
                if char != ",":
                    raise JsonStreamError("Ungültiges JSON-Objekt.")
                self.write(char)
        elif char == "[":
            self.write(self.take())
            self.whitespace()
            if self.peek() == "]":
                self.write(self.take())
                return
            while True:
                self.value(depth + 1)
                self.whitespace()
                char = self.take()
                if char == "]":
                    self.write(char)
                    return
                if char != ",":
                    raise JsonStreamError("Ungültiges JSON-Array.")
                self.write(char)
        elif char == "t":
            self.literal("true")
        elif char == "f":
            self.literal("false")
        elif char == "n":
            self.literal("null")
        elif char == "-" or char.isdigit():
            self.number()
        else:
            raise JsonStreamError("Ungültiger JSON-Wert.")
        self.report()

    def run(self) -> tuple[int, int]:
        self.whitespace()
        if not self.peek():
            raise JsonStreamError("JSON-Datei ist leer.")
        self.value()
        self.whitespace()
        if self.peek():
            raise JsonStreamError("Unerwartete Daten nach dem JSON-Wert.")
        self.report()
        return self.replacements, self.lines


def sanitize_json_stream(
    source: TextIO,
    destination: TextIO,
    rules: list[tuple[SanitizationRule, re.Pattern[str]]],
    project_id: str | None,
    cancel_check: CancelCheck | None = None,
    progress_callback: ProgressCallback | None = None,
    total_bytes: int = 0,
) -> tuple[int, int]:
    parser = _Parser(
        source, destination, rules, project_id, True,
        cancel_check, progress_callback, total_bytes,
    )
    return parser.run()


def validate_json_stream(
    source: TextIO,
    rules: list[tuple[SanitizationRule, re.Pattern[str]]],
    cancel_check: CancelCheck | None = None,
) -> None:
    parser = _Parser(source, None, rules, None, False, cancel_check, None, 0)
    parser.run()
