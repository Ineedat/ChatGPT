"""Versioned JSON rule configuration and deterministic conflict checks.

This module validates configuration only. It does not execute rules or sanitize logs.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIG_VERSION = 1
DEFAULT_RULES_DIR = ".logsanitizer/rules"


class RuleProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
    name: str = Field(min_length=1, max_length=100)
    source_hint: str | None = Field(default=None, max_length=200)


class SanitizationRule(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)
    match_type: Literal["plain", "regex"]
    pattern: str = Field(min_length=1, max_length=2000)
    replacement: str = Field(min_length=1, max_length=200)
    case_sensitive: bool = False
    priority: int = Field(default=100, ge=1, le=10000)
    profile_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
    enabled: bool = True

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Das Suchmuster darf nicht leer sein.")
        return value

    @model_validator(mode="after")
    def validate_regex(self) -> SanitizationRule:
        if self.match_type == "regex":
            try:
                re.compile(self.pattern, 0 if self.case_sensitive else re.IGNORECASE)
            except re.error as exc:
                raise ValueError("Ungültiger regulärer Ausdruck.") from exc
        return self


class RuleConfig(BaseModel):
    """Versioned collection of shared rules and optional source-specific profiles."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = CONFIG_VERSION
    profiles: list[RuleProfile] = Field(default_factory=list, max_length=200)
    rules: list[SanitizationRule] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def validate_references_and_ids(self) -> RuleConfig:
        profile_ids = [profile.id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("Profil-IDs müssen eindeutig sein.")
        rule_ids = [rule.id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("Regel-IDs müssen eindeutig sein.")
        known_profiles = set(profile_ids)
        if any(rule.profile_id is not None and rule.profile_id not in known_profiles for rule in self.rules):
            raise ValueError("Eine Regel verweist auf ein nicht definiertes Quellprofil.")
        return self


def find_rule_conflicts(config: RuleConfig) -> list[dict[str, str]]:
    """Return exact-match conflicts where same-scope rules share a priority."""
    conflicts: list[dict[str, str]] = []
    seen: dict[tuple[str | None, str, str, bool, int], str] = {}
    for rule in config.rules:
        if not rule.enabled:
            continue
        pattern = rule.pattern if rule.case_sensitive else rule.pattern.casefold()
        key = (rule.profile_id, rule.match_type, pattern, rule.case_sensitive, rule.priority)
        previous_id = seen.get(key)
        if previous_id is not None:
            conflicts.append({
                "rule_id": rule.id,
                "conflicts_with": previous_id,
                "reason": "Gleiches Suchmuster, gleicher Geltungsbereich und gleiche Priorität.",
            })
        else:
            seen[key] = rule.id
    return conflicts


def rules_directory() -> Path:
    configured = os.environ.get("LOGSANITIZER_RULES_DIR")
    return Path(configured).expanduser() if configured else Path.home() / DEFAULT_RULES_DIR


def config_path() -> Path:
    return rules_directory() / "rules-v1.json"


def load_rule_config() -> RuleConfig:
    path = config_path()
    if not path.exists():
        return RuleConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Die lokale Regelkonfiguration kann nicht gelesen werden.") from exc
    return RuleConfig.model_validate(raw)


def save_rule_config(config: RuleConfig) -> None:
    """Atomically persist validated configuration; keep local files owner-only where supported."""
    directory = rules_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    target = directory / "rules-v1.json"
    payload = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".rules-", suffix=".tmp", dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(target)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    finally:
        temporary.unlink(missing_ok=True)
