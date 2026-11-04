from pathlib import Path

import pytest

from logsanitizer.rule_config import RuleConfig
from logsanitizer.rule_file_preview import preview_file_window
from logsanitizer.rule_preview import RulePreviewError


def sample_config() -> RuleConfig:
    return RuleConfig.model_validate({
        "schema_version": 1,
        "profiles": [],
        "rules": [{
            "id": "ip", "name": "IP", "category": "network",
            "match_type": "plain", "pattern": "192.0.2.17",
            "replacement": "[IP]", "replacement_mode": "fixed",
            "case_sensitive": True, "priority": 10, "enabled": True,
        }],
    })


def test_preview_file_window_reads_only_a_bounded_start_window(tmp_path: Path) -> None:
    source = tmp_path / "application.log"
    source.write_text(("client=192.0.2.17\n" * 5000), encoding="utf-8")
    original = source.read_bytes()

    result = preview_file_window(source, sample_config())

    assert result["original_text"].startswith("client=192.0.2.17")
    assert result["preview_text"].startswith("client=[IP]")
    assert result["window_chars"] <= 65_536
    assert result["has_next"] is True
    assert source.read_bytes() == original


def test_preview_file_window_can_open_the_end_of_a_large_file(tmp_path: Path) -> None:
    source = tmp_path / "application.log"
    source.write_text(("line-start\n" + "x" * 100 + "\n") * 5000 + "END-OF-LOG\n", encoding="utf-8")

    result = preview_file_window(source, sample_config(), from_end=True)

    assert "END-OF-LOG" in result["original_text"]
    assert result["source_offset"] > 0
    assert result["has_previous"] is True
    assert result["has_next"] is False


def test_preview_file_window_aligns_offsets_to_complete_utf8_lines(tmp_path: Path) -> None:
    source = tmp_path / "unicode.log"
    source.write_text(("äöü-192.0.2.17\n" * 1000), encoding="utf-8")

    result = preview_file_window(source, sample_config(), byte_offset=7)

    assert result["original_text"].startswith("äöü-192.0.2.17")
    assert "�" not in result["original_text"]


def test_preview_file_window_rejects_invalid_utf8(tmp_path: Path) -> None:
    source = tmp_path / "invalid.log"
    source.write_bytes(b"valid line\ninvalid-\xff-line\n")

    with pytest.raises(RulePreviewError, match="UTF-8"):
        preview_file_window(source, sample_config())


def test_preview_file_window_rejects_symlinks(tmp_path: Path) -> None:
    source = tmp_path / "source.log"
    source.write_text("safe\n", encoding="utf-8")
    link = tmp_path / "link.log"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not available on this platform")

    with pytest.raises(RulePreviewError, match="nicht verfügbar"):
        preview_file_window(link, sample_config())
