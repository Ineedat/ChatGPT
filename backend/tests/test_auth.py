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


def _admin_client(username, password):
    client = TestClient(app)
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": client.cookies.get("logsanitizer_csrf")})
    return client


def test_admin_can_update_roles_and_disable_user_and_sessions_are_revoked(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("root-admin", "root-admin-password-123", ["admin"])
    target_id = create_user("temporary-user", "temporary-password-123", ["operator"])
    with _admin_client("root-admin", "root-admin-password-123") as admin, \
         _admin_client("temporary-user", "temporary-password-123") as target:
        changed = admin.put(
            f"/api/auth/users/{target_id}",
            json={"roles": ["reviewer", "approver"]},
        )
        assert changed.status_code == 200
        assert set(changed.json()["roles"]) == {"reviewer", "approver"}
        disabled = admin.put(
            f"/api/auth/users/{target_id}", json={"enabled": False}
        )
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False
        assert target.get("/api/auth/me").status_code == 401
        assert admin.put(
            f"/api/auth/users/{target_id}", json={"enabled": True}
        ).json()["enabled"] is True


def test_admin_cannot_remove_last_admin_or_self_lockout(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("only-admin", "only-admin-password-123", ["admin"])
    with _admin_client("only-admin", "only-admin-password-123") as admin:
        users = admin.get("/api/auth/users").json()
        admin_id = users[0]["id"]
        assert admin.delete(f"/api/auth/users/{admin_id}").status_code == 409
        assert admin.put(
            f"/api/auth/users/{admin_id}", json={"roles": ["operator"]}
        ).status_code == 409
        assert admin.put(
            f"/api/auth/users/{admin_id}", json={"enabled": False}
        ).status_code == 409
        assert admin.get("/api/auth/me").status_code == 200


def test_admin_can_delete_another_admin_when_a_second_active_admin_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("primary-admin", "primary-admin-password-123", ["admin"])
    secondary_id = create_user("secondary-admin", "secondary-admin-password-123", ["admin"])
    with _admin_client("primary-admin", "primary-admin-password-123") as admin:
        deleted = admin.delete(f"/api/auth/users/{secondary_id}")
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": True, "id": secondary_id}
        assert all(row["username"] != "secondary-admin" for row in admin.get("/api/auth/users").json())


def test_user_administration_rejects_invalid_roles_and_non_admins(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("regular-user", "regular-user-password-123", ["operator"])
    create_user("administrator", "administrator-password-123", ["admin"])
    target_id = 1
    with _admin_client("administrator", "administrator-password-123") as admin, \
         _admin_client("regular-user", "regular-user-password-123") as regular:
        assert admin.put(
            f"/api/auth/users/{target_id}", json={"roles": ["not-a-role"]}
        ).status_code == 422
        assert regular.delete(f"/api/auth/users/{target_id}").status_code == 403


def test_api_route_role_matrix_covers_every_registered_route():
    from logsanitizer.auth import _API_ROLE_POLICIES, _role_access_allowed, _route_template_matches
    from logsanitizer.main import app

    role_sets = {
        "admin": {"admin"},
        "operator": {"operator"},
        "reviewer": {"reviewer"},
        "approver": {"approver"},
        "rule_owner": {"rule_owner"},
        "combined": {"operator", "reviewer", "rule_owner"},
    }
    api_routes = [
        route for route in app.routes
        if getattr(route, "path", "").startswith("/api/")
        and getattr(route, "methods", None)
    ]
    assert api_routes, "The API route inventory must not be empty"

    for route in api_routes:
        path = route.path
        for method in route.methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            if path == "/api/health":
                continue
            matching_policies = [
                policy for policy in _API_ROLE_POLICIES
                if policy[0] == method and _route_template_matches(policy[1], path)
            ]
            assert len(matching_policies) == 1, (
                f"API route must have exactly one authorization rule: {method} {path}; "
                f"found {len(matching_policies)}"
            )
            expected_roles = matching_policies[0][2]
            for role_name, roles in role_sets.items():
                assert _role_access_allowed(path, method, roles) is bool(
                    roles.intersection(expected_roles)
                ), f"Unexpected authorization for {method} {path} and {role_name}"


def test_unclassified_api_routes_are_denied_by_default():
    from logsanitizer.auth import _role_access_allowed

    for roles in ({"operator"}, {"reviewer"}, {"approver"}, {"rule_owner"}, set()):
        assert not _role_access_allowed("/api/new-unclassified-endpoint", "GET", roles)
    assert not _role_access_allowed("/api/new-unclassified-endpoint", "GET", {"admin"})


def test_role_changes_take_effect_for_existing_sessions_immediately(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    create_user("role-admin", "role-admin-password-123", ["admin"])
    target_id = create_user("role-target", "role-target-password-123", ["operator"])

    with _admin_client("role-admin", "role-admin-password-123") as admin:
        with _admin_client("role-target", "role-target-password-123") as target:
            assert target.post("/api/projects", json={"name": "Before role change"}).status_code == 201

            changed = admin.put(
                f"/api/auth/users/{target_id}",
                json={"roles": ["reviewer"]},
            )
            assert changed.status_code == 200
            assert target.get("/api/projects").status_code == 403
            assert target.get("/api/reviews/queue").status_code == 200
            assert target.get("/api/auth/me").json()["roles"] == ["reviewer"]
