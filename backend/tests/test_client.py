"""Test client that authenticates existing feature tests as a local operator."""
import secrets
from fastapi.testclient import TestClient as BaseTestClient
from logsanitizer.auth import create_user
from logsanitizer.main import app

class TestClient(BaseTestClient):
    def __enter__(self):
        super().__enter__()
        username = "test-" + secrets.token_hex(6)
        password = "test-password-" + secrets.token_hex(8)
        create_user(username, password, ["admin", "operator", "reviewer", "approver"])
        response = super().post("/api/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.text
        self._test_csrf = self.cookies.get("logsanitizer_csrf")
        return self

    def request(self, method, url, **kwargs):
        if method.upper() not in {"GET", "HEAD", "OPTIONS"} and getattr(self, "_test_csrf", None):
            headers = dict(kwargs.get("headers") or {})
            headers["X-CSRF-Token"] = self._test_csrf
            kwargs["headers"] = headers
        return super().request(method, url, **kwargs)
