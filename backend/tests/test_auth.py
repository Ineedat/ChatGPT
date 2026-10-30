from fastapi.testclient import TestClient

from logsanitizer.auth import create_user
from logsanitizer.main import app


def test_login_rejects_invalid_credentials_and_protects_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("operator", "correct-horse-battery", ["operator"])
    with TestClient(app) as client:
        assert client.get("/api/projects").status_code == 401
        failed = client.post("/api/auth/login", json={"username":"operator","password":"wrong-password"})
        assert failed.status_code == 401
        success = client.post("/api/auth/login", json={"username":"operator","password":"correct-horse-battery"})
        assert success.status_code == 200
        assert client.get("/api/auth/me").json()["roles"] == ["operator"]
        assert client.get("/api/projects").status_code == 200

def test_role_assignment_and_csrf_are_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("reviewer", "reviewer-password-123", ["reviewer"])
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"username":"reviewer","password":"reviewer-password-123"})
        assert client.get("/api/auth/users").status_code == 403
        assert client.post("/api/projects", json={"name":"Denied"}).status_code == 403
        csrf = client.cookies.get("logsanitizer_csrf")
        assert client.post("/api/auth/logout").status_code == 403
        assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
        assert client.get("/api/projects").status_code == 401

def test_password_hash_is_not_stored_as_plaintext(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("secure-user", "long-password-123", ["admin", "operator"])
    import sqlite3
    db = sqlite3.connect(tmp_path / "data" / "auth.sqlite3")
    stored = db.execute("SELECT password_hash FROM users").fetchone()[0]
    db.close()
    assert stored.startswith("scrypt$")
    assert stored != "long-password-123"

def test_expired_session_is_rejected(tmp_path, monkeypatch):
    import hashlib
    import sqlite3
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("expiry-user", "expiry-password-123", ["operator", "reviewer"])
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"username":"expiry-user","password":"expiry-password-123"})
        roles = client.get("/api/auth/me").json()["roles"]
        assert set(roles) == {"operator", "reviewer"}
        token = client.cookies.get("logsanitizer_session")
        db = sqlite3.connect(tmp_path / "data" / "auth.sqlite3")
        db.execute("UPDATE sessions SET expires_at=0 WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
        db.commit()
        db.close()
        assert client.get("/api/auth/me").status_code == 401



def test_login_attempts_are_rate_limited_and_docs_require_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("rate-limited", "rate-limit-password-123", ["operator"])
    with TestClient(app) as client:
        assert client.get("/api/docs").status_code == 401
        assert client.get("/api/openapi.json").status_code == 401
        for _ in range(5):
            response = client.post(
                "/api/auth/login",
                json={"username": "rate-limited", "password": "wrong-password"},
            )
            assert response.status_code == 401
        locked = client.post(
            "/api/auth/login",
            json={"username": "rate-limited", "password": "rate-limit-password-123"},
        )
        assert locked.status_code == 429



def test_role_matrix_keeps_operator_and_review_permissions_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("operator-only", "operator-password-123", ["operator"])
    create_user("reviewer-only", "reviewer-password-123", ["reviewer"])
    create_user("approver-only", "approver-password-123", ["approver"])
    create_user("admin-only", "admin-password-123", ["admin"])
    create_user("combined", "combined-password-123", ["operator", "reviewer"])

    def authenticated(username, password):
        client = TestClient(app)
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert response.status_code == 200
        client.headers.update({
            "X-CSRF-Token": client.cookies.get("logsanitizer_csrf")
        })
        return client

    with authenticated("operator-only", "operator-password-123") as operator, \
         authenticated("reviewer-only", "reviewer-password-123") as reviewer, \
         authenticated("approver-only", "approver-password-123") as approver, \
         authenticated("admin-only", "admin-password-123") as admin, \
         authenticated("combined", "combined-password-123") as combined:
        # Operators may manage projects and sanitize, but cannot enter the review workspace.
        assert operator.post("/api/projects", json={"name": "Operator project"}).status_code == 201
        assert operator.get("/api/reviews/queue").status_code == 403
        assert operator.get("/api/reviews/audit").status_code == 403

        # Reviewer and approver roles can access review data, but cannot manage projects.
        for client in (reviewer, approver):
            assert client.get("/api/reviews/queue").status_code == 200
            assert client.get("/api/reviews/audit").status_code == 200
            assert client.post("/api/projects", json={"name": "Denied"}).status_code == 403
            assert client.get("/api/auth/users").status_code == 403

        # User administration remains exclusive to admins.
        assert admin.get("/api/auth/users").status_code == 200
        created = admin.post(
            "/api/auth/users",
            json={
                "username": "managed-user",
                "password": "managed-password-123",
                "roles": ["operator", "reviewer"],
            },
        )
        assert created.status_code == 201
        assert operator.get("/api/auth/users").status_code == 403

        # Multiple roles can be bound to one account without losing either permission set.
        assert set(combined.get("/api/auth/me").json()["roles"]) == {"operator", "reviewer"}
        assert combined.post("/api/projects", json={"name": "Combined project"}).status_code == 201
        assert combined.get("/api/reviews/queue").status_code == 200


def test_csrf_cookie_is_readable_from_frontend_root_path(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("csrf-admin", "csrf-admin-password-123", ["admin", "operator"])

    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "csrf-admin", "password": "csrf-admin-password-123"},
        )
        assert login.status_code == 200
        set_cookie_headers = login.headers.get_list("set-cookie")
        csrf_cookie = next(
            header for header in set_cookie_headers
            if header.startswith("logsanitizer_csrf=") and "Max-Age=0" not in header
        )
        session_cookie = next(
            header for header in set_cookie_headers
            if header.startswith("logsanitizer_session=")
        )
        assert "Path=/" in csrf_cookie
        assert "HttpOnly" not in csrf_cookie
        assert "Path=/api" in session_cookie
        assert "HttpOnly" in session_cookie

        csrf = client.cookies.get("logsanitizer_csrf")
        created = client.post(
            "/api/projects",
            json={"name": "CSRF cookie project"},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201



def test_rule_owner_can_manage_rules_but_cannot_process_or_manage_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("rule-owner", "rule-owner-password-123", ["rule_owner"])
    create_user("processor", "processor-password-123", ["operator"])

    def login(username, password):
        client = TestClient(app)
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200
        client.headers.update({"X-CSRF-Token": client.cookies.get("logsanitizer_csrf")})
        return client

    with login("rule-owner", "rule-owner-password-123") as owner, login("processor", "processor-password-123") as processor:
        payload = {"schema_version": 1, "profiles": [], "rules": []}
        assert owner.put("/api/rules/config", json=payload).status_code == 200
        assert owner.post("/api/projects", json={"name": "Denied project"}).status_code == 403
        assert processor.put("/api/rules/config", json=payload).status_code == 403
        assert processor.post("/api/projects", json={"name": "Allowed project"}).status_code == 201
