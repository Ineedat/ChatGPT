"""Optional SMTP notifications for review workflow events.

SMTP credentials and recipient lists are read only from the local process environment;
they are never returned by the API or written to the review database.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import getaddresses

LOGGER = logging.getLogger(__name__)
SMTP_TIMEOUT_SECONDS = 10


def _enabled(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _recipients(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    addresses = [address.strip() for _, address in getaddresses([raw]) if address.strip()]
    return [
        address for address in addresses
        if "@" in address
        and not any(ord(char) < 32 for char in address)
        and len(address) <= 254
    ]


def _safe_text(value: object, limit: int = 200) -> str:
    text = str(value or "")
    return "".join(char for char in text if char in "\t " or ord(char) >= 32 and ord(char) != 127)[:limit]


def send_notification(recipients: list[str], subject: str, body: str) -> bool:
    """Send one plain-text message; return False when disabled or delivery fails."""
    if not recipients:
        return False
    host = os.environ.get("LOGSANITIZER_SMTP_HOST", "").strip()
    sender = os.environ.get("LOGSANITIZER_SMTP_FROM", "").strip()
    if not host or not sender:
        return False
    try:
        port = int(os.environ.get("LOGSANITIZER_SMTP_PORT", "587"))
        if not 1 <= port <= 65535:
            raise ValueError("SMTP port out of range")
        security = os.environ.get("LOGSANITIZER_SMTP_SECURITY", "starttls").strip().casefold()
        if security not in {"starttls", "ssl", "none"}:
            raise ValueError("unsupported SMTP security mode")
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        message.set_content(body)
        context = ssl.create_default_context()
        if security == "ssl":
            with smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT_SECONDS, context=context) as smtp:
                _login_if_configured(smtp)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
                smtp.ehlo()
                if security == "starttls":
                    smtp.starttls(context=context)
                    smtp.ehlo()
                _login_if_configured(smtp)
                smtp.send_message(message)
        return True
    except (OSError, ValueError, smtplib.SMTPException) as exc:
        # Never log credentials, message bodies, or recipient lists.
        LOGGER.warning("SMTP review notification failed (%s).", type(exc).__name__)
        return False


def _login_if_configured(smtp: smtplib.SMTP) -> None:
    username = os.environ.get("LOGSANITIZER_SMTP_USERNAME", "")
    password = os.environ.get("LOGSANITIZER_SMTP_PASSWORD", "")
    if username or password:
        if not username or not password:
            raise ValueError("Both SMTP username and password must be configured.")
        smtp.login(username, password)


def notify_pending_review(run: dict[str, object]) -> bool:
    if run.get("status") != "pending_review":
        return False
    recipients = _recipients("LOGSANITIZER_REVIEWER_EMAILS")
    run_id = _safe_text(run.get("id"), 80)
    display_name = _safe_text(run.get("display_name"), 200)
    subject = f"LogSanitizer: Prüfung erforderlich ({run_id})"
    body = (
        "Ein bereinigter Lauf wartet auf die bewusste Prüfung in LogSanitizer.\n\n"
        f"Lauf-ID: {run_id}\n"
        f"Quelldatei: {display_name}\n"
        "Öffnen Sie die lokale Anwendung und prüfen Sie die Ausgabe über die Prüfer-Warteschlange.\n"
        "Diese E-Mail enthält keine Loginhalte und keinen absoluten Dateipfad.\n"
    )
    return send_notification(recipients, subject, body)


def notify_returned_run(run: dict[str, object]) -> bool:
    if run.get("status") != "returned":
        return False
    recipients = _recipients("LOGSANITIZER_OPERATOR_EMAILS")
    run_id = _safe_text(run.get("id"), 80)
    display_name = _safe_text(run.get("display_name"), 200)
    subject = f"LogSanitizer: Lauf zurückgegeben ({run_id})"
    body = (
        "Ein geprüfter Lauf wurde zur Überarbeitung zurückgegeben.\n\n"
        f"Lauf-ID: {run_id}\n"
        f"Quelldatei: {display_name}\n"
        "Bitte öffnen Sie die lokale Anwendung, lesen Sie den Kommentar in der Laufhistorie "
        "und bereinigen Sie die Datei nach Anpassung der Regeln erneut.\n"
        "Diese E-Mail enthält keine Loginhalte, Kommentare oder absoluten Dateipfade.\n"
    )
    return send_notification(recipients, subject, body)
