from __future__ import annotations

from email.message import EmailMessage

from logsanitizer import notifications


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, **kwargs):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.messages: list[EmailMessage] = []
        self.started_tls = False
        self.logged_in = False
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def ehlo(self):
        return None

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, username, password):
        self.logged_in = (username, password) == ("smtp-user", "smtp-password")

    def send_message(self, message):
        self.messages.append(message)


def _configure(monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("LOGSANITIZER_SMTP_PORT", "587")
    monkeypatch.setenv("LOGSANITIZER_SMTP_FROM", "logsanitizer@example.invalid")
    monkeypatch.setenv("LOGSANITIZER_SMTP_SECURITY", "starttls")
    monkeypatch.setenv("LOGSANITIZER_SMTP_USERNAME", "smtp-user")
    monkeypatch.setenv("LOGSANITIZER_SMTP_PASSWORD", "smtp-password")
    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.instances.clear()


def test_pending_review_notification_uses_configured_recipients_and_no_log_contents(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("LOGSANITIZER_REVIEWER_EMAILS", "reviewer@example.invalid,second@example.invalid")

    sent = notifications.notify_pending_review({
        "id": "run-123", "status": "pending_review", "display_name": "application.log",
        "output_path": "/sensitive/private/clean.log", "last_comment": "secret details",
    })

    assert sent is True
    smtp = FakeSMTP.instances[0]
    assert smtp.started_tls is True
    assert smtp.logged_in is True
    assert smtp.messages[0]["To"] == "reviewer@example.invalid, second@example.invalid"
    assert "Prüfung erforderlich" in smtp.messages[0]["Subject"]
    body = smtp.messages[0].get_content()
    assert "application.log" in body
    assert "/sensitive/private" not in body
    assert "secret details" not in body


def test_return_notification_goes_to_operator_list_without_comment(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("LOGSANITIZER_OPERATOR_EMAILS", "operator@example.invalid")

    sent = notifications.notify_returned_run({
        "id": "run-456", "status": "returned", "display_name": "service.log",
        "last_comment": "contains sensitive information",
    })

    assert sent is True
    message = FakeSMTP.instances[0].messages[0]
    assert message["To"] == "operator@example.invalid"
    assert "zurückgegeben" in message["Subject"]
    assert "contains sensitive information" not in message.get_content()


def test_notifications_are_disabled_without_smtp_host(monkeypatch):
    monkeypatch.delenv("LOGSANITIZER_SMTP_HOST", raising=False)
    monkeypatch.delenv("LOGSANITIZER_SMTP_FROM", raising=False)
    monkeypatch.setenv("LOGSANITIZER_REVIEWER_EMAILS", "reviewer@example.invalid")
    assert notifications.notify_pending_review({
        "id": "run-1", "status": "pending_review", "display_name": "service.log"
    }) is False


def test_notification_skips_unconfigured_recipients(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.delenv("LOGSANITIZER_REVIEWER_EMAILS", raising=False)
    assert notifications.notify_pending_review({
        "id": "run-1", "status": "pending_review", "display_name": "service.log"
    }) is False


def test_invalid_security_mode_fails_closed(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("LOGSANITIZER_SMTP_SECURITY", "insecure")
    assert notifications.send_notification(
        ["reviewer@example.invalid"], "subject", "body"
    ) is False
