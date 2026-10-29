"""Resource-bound regression tests for the streaming sanitizer.

The regular CI test uses a moderate fixture to catch accidental whole-file reads.
Set LOGSANITIZER_RUN_5GB_TEST=1 to run the opt-in 5 GiB end-to-end test.
"""
# ruff: noqa: I001

import os
import pathlib
import tracemalloc

import pytest

from logsanitizer.rule_config import RuleConfig
from logsanitizer.sanitizer import sanitize_file


CHUNK = (b"2026-10-29T12:00:00Z INFO service request completed\n" * 16_384)
CHUNK_BYTES = len(CHUNK)


def _write_repeated_file(path: pathlib.Path, size_bytes: int) -> None:
    """Create a file incrementally without holding the complete fixture in memory."""
    full_chunks, remainder = divmod(size_bytes, CHUNK_BYTES)
    with path.open("wb") as stream:
        for _ in range(full_chunks):
            stream.write(CHUNK)
        if remainder:
            stream.write(CHUNK[:remainder])


def _plain_config() -> RuleConfig:
    return RuleConfig.model_validate({"schema_version": 1, "profiles": [], "rules": []})


def _assert_streaming_run(source: pathlib.Path, destination: pathlib.Path) -> dict[str, int | str]:
    result = sanitize_file(source, destination, _plain_config(), format_name="text")
    assert result["status"] == "completed"
    assert result["validated"] is True
    assert result["input_bytes"] == source.stat().st_size
    assert result["output_bytes"] == source.stat().st_size
    assert destination.stat().st_size == source.stat().st_size
    return result


def test_large_file_processing_uses_bounded_python_memory(tmp_path: pathlib.Path) -> None:
    """A 64 MiB input must not be materialized as one Python bytes/string object."""
    source = tmp_path / "large.log"
    destination = tmp_path / "large.clean.log"
    _write_repeated_file(source, 64 * 1024 * 1024)

    tracemalloc.start()
    try:
        result = _assert_streaming_run(source, destination)
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert result["lines_processed"] > 1_000_000
    # The engine's 1 MiB line cap bounds per-line allocations. Leave headroom
    # for Python/regex/runtime bookkeeping while detecting whole-file buffering.
    assert peak_bytes < 16 * 1024 * 1024


@pytest.mark.skipif(
    os.environ.get("LOGSANITIZER_RUN_5GB_TEST") != "1",
    reason="Set LOGSANITIZER_RUN_5GB_TEST=1 for the resource-intensive 5 GiB test.",
)
def test_five_gibibyte_file_streams_end_to_end(tmp_path: pathlib.Path) -> None:
    """Opt-in release qualification: generate, sanitize and verify a 5 GiB log."""
    source = tmp_path / "five-gib.log"
    destination = tmp_path / "five-gib.clean.log"
    target_size = 5 * 1024 * 1024 * 1024
    _write_repeated_file(source, target_size)

    result = _assert_streaming_run(source, destination)

    assert result["input_bytes"] == target_size
    assert result["output_bytes"] == target_size
    assert result["lines_processed"] > 80_000_000
