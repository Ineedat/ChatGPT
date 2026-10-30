"""Generate and process a synthetic large log while recording resource metrics.

Example:
  python packaging/benchmark_sanitizer.py --size-gib 5 --work-dir ./benchmark-data

Only synthetic data is generated. The script never reads real log files.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from logsanitizer.rule_config import RuleConfig
from logsanitizer.sanitizer import sanitize_file


def peak_rss_bytes() -> int | None:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return int(counters.PeakWorkingSetSize)
        except (AttributeError, OSError):
            return None
        return None
    try:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value * (1024 if platform.system() != "Darwin" else 1))
    except (ImportError, OSError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size-gib", type=float, default=5.0)
    parser.add_argument("--work-dir", type=Path, default=Path("benchmark-data"))
    args = parser.parse_args()
    if not 0.01 <= args.size_gib <= 20:
        parser.error("--size-gib muss zwischen 0.01 und 20 liegen.")

    work_dir = args.work_dir.expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    source = work_dir / "synthetic-large.log"
    output = work_dir / "synthetic-large.cleaned.log"
    source.unlink(missing_ok=True)
    output.unlink(missing_ok=True)

    line = b"timestamp=2026-10-30T12:00:00Z user=alice ip=192.0.2.10 event=synthetic-test\n"
    target_bytes = int(args.size_gib * 1024**3)
    block = line * max(1, (4 * 1024 * 1024) // len(line))
    written = 0
    with source.open("wb") as stream:
        while written < target_bytes:
            chunk = block[: min(len(block), target_bytes - written)]
            stream.write(chunk)
            written += len(chunk)

    config = RuleConfig.model_validate({
        "schema_version": 1,
        "profiles": [],
        "rules": [{
            "id": "synthetic-user",
            "name": "Synthetic user",
            "category": "username",
            "match_type": "plain",
            "pattern": "user=alice",
            "replacement": "user=[USER]",
            "priority": 10,
        }],
    })

    tracemalloc.start()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    result = sanitize_file(source, output, config, format_name="text")
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    _current, peak_python = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    report = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "input_bytes": source.stat().st_size,
        "output_bytes": output.stat().st_size,
        "wall_seconds": round(wall_seconds, 3),
        "cpu_seconds": round(cpu_seconds, 3),
        "throughput_mib_per_second": round(source.stat().st_size / 1024**2 / wall_seconds, 2),
        "peak_python_tracemalloc_bytes": peak_python,
        "peak_process_rss_bytes": peak_rss_bytes(),
        "lines_processed": result["lines_processed"],
        "replacements": result["replacements"],
        "validated": result["validated"],
        "validation_scope": result["validation_scope"],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not result["validated"] or output.stat().st_size == 0:
        raise SystemExit("Benchmark result failed validation.")
    print(f"Synthetic input and output retained in: {work_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def test_json_document_sanitization_job_is_available_through_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(config())
    source = tmp_path / "events.json"
    original = b'{"message":"secret=alpha"}'
    source.write_bytes(original)
    output = tmp_path / "events.cleaned.json"

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "JSON document"}).json()["id"]
        imported = client.post(
            f"/api/projects/{project_id}/files", json={"path": str(source)}
        ).json()
        changed = client.put(
            f"/api/projects/{project_id}/files/{imported['id']}/format",
            json={"format_override": "json"},
        )
        assert changed.status_code == 200
        started = client.post(
            f"/api/projects/{project_id}/files/{imported['id']}/sanitize-jobs",
            json={"output_path": str(output)},
        )
        assert started.status_code == 202
        job_id = started.json()["id"]
        state = client.get(
            f"/api/projects/{project_id}/files/{imported['id']}/sanitize-jobs/{job_id}"
        ).json()
        assert state["status"] == "completed"
        assert state["result"]["validated"] is True

    assert output.read_bytes() == b'{"message":"hidden=REDACTED"}'
    assert source.read_bytes() == original
