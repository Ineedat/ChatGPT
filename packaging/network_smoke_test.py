"""Smoke-test a portable bundle with the network profile and local TLS.

This verifies packaged startup and HTTPS health with LDAP/SMTP configured. It
does not contact a real directory or mail server; those remain target-site tests.
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def make_certificate(root: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = root / "network.crt", root / "network.key"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    if os.name != "nt":
        key_path.chmod(0o600)
    return cert_path, key_path


def main() -> int:
    bundle = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/LogSanitizer").resolve()
    executable = bundle / ("LogSanitizer.exe" if os.name == "nt" else "LogSanitizer")
    if not executable.is_file():
        raise SystemExit(f"Bundle executable not found: {executable}")

    with tempfile.TemporaryDirectory(prefix="logsanitizer-network-smoke-") as temp:
        root = Path(temp)
        cert, key = make_certificate(root)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        config_path = root / "deployment.json"
        config_path.write_text(json.dumps({
            "profile": "network",
            "data_dir": str(root / "data"),
            "server": {
                "bind_host": "0.0.0.0",
                "port": port,
                "tls_certfile": str(cert),
                "tls_keyfile": str(key),
            },
            "auth": {"provider": "ldap"},
            "ldap": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 636,
                "use_ssl": True,
                "start_tls": False,
                "bind_dn": "CN=smoke-reader,DC=example,DC=invalid",
                "user_search_base": "DC=example,DC=invalid",
                "role_groups": {
                    "admin": "CN=Admins,DC=example,DC=invalid",
                    "operator": "CN=Operators,DC=example,DC=invalid",
                    "reviewer": "CN=Reviewers,DC=example,DC=invalid",
                    "approver": "CN=Approvers,DC=example,DC=invalid",
                },
            },
            "smtp": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 2525,
                "security": "starttls",
                "from": "logsanitizer@example.invalid",
                "reviewer_emails": "reviewers@example.invalid",
                "operator_emails": "operators@example.invalid",
            },
        }), encoding="utf-8")
        env = os.environ.copy()
        env["LOGSANITIZER_CONFIG"] = str(config_path)
        env["LOGSANITIZER_LDAP_BIND_PASSWORD"] = "synthetic-smoke-password"
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
            context = ssl._create_unverified_context()
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    output = process.stdout.read() if process.stdout else ""
                    raise RuntimeError(f"Network profile exited early ({process.returncode}):\n{output}")
                try:
                    with urllib.request.urlopen(
                        f"https://127.0.0.1:{port}/api/health",
                        timeout=1,
                        context=context,
                    ) as response:
                        if response.status == 200:
                            print("Portable network-profile HTTPS health check passed.")
                            return 0
                except (OSError, TimeoutError):
                    time.sleep(0.25)
            raise RuntimeError("Network profile did not become healthy within 25 seconds.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
