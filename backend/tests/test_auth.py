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
        token = client.cookies.get("logsanitizer_session")
        db = sqlite3.connect(tmp_path / "data" / "auth.sqlite3")
        db.execute("UPDATE sessions SET expires_at=0 WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
        db.commit()
        db.close()
        assert client.get("/api/auth/me").status_code == 401
