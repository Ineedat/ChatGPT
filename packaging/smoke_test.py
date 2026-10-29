"""Smoke-test a portable standalone bundle without touching real user data."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    bundle = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/LogSanitizer")
    executable = bundle / ("LogSanitizer.exe" if os.name == "nt" else "LogSanitizer")
    if not executable.is_file():
        raise SystemExit(f"Bundle executable not found: {executable}")

    with tempfile.TemporaryDirectory(prefix="logsanitizer-smoke-") as temp:
        root = Path(temp)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        config_path = root / "deployment.json"
        config_path.write_text(
            json.dumps({
                "profile": "standalone",
                "data_dir": str(root / "data"),
                "server": {
                    "bind_host": "127.0.0.1",
                    "port": port,
                    "tls_certfile": "",
                    "tls_keyfile": "",
                },
                "auth": {"provider": "local"},
                "ldap": {"enabled": False},
                "smtp": {"enabled": False},
            }),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["LOGSANITIZER_CONFIG"] = str(config_path)
        env["LOGSANITIZER_DATA_DIR"] = str(root / "data")
        process = subprocess.Popen(
            [str(executable)],
            cwd=str(bundle),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    output = process.stdout.read() if process.stdout else ""
                    raise RuntimeError(f"Portable app exited early ({process.returncode}):\n{output}")
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/health", timeout=1
                    ) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                        if response.status == 200 and payload.get("application") == "LogSanitizer":
                            print("Portable standalone health check passed.")
                            return 0
                except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                    time.sleep(0.25)
            raise RuntimeError("Portable app did not become healthy within 25 seconds.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
