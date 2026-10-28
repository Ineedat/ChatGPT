import sqlite3

from fastapi.testclient import TestClient as BaseTestClient

from logsanitizer.auth import create_user
from logsanitizer.main import app
from logsanitizer.rule_config import RuleConfig, save_rule_config


def _config():
    return RuleConfig.model_validate({
        "schema_version": 1,
        "profiles": [],
        "rules": [{
            "id": "secret-rule",
            "name": "Secret token",
            "category": "secret",
            "match_type": "regex",
            "pattern": r"secret=[A-Za-z0-9]+",
            "replacement": "REDACTED",
            "priority": 10,
        }],
    })


def _sanitized_run(client, tmp_path, name="app.log", contents=b"secret=alpha\n"):
    source = tmp_path / name
    source.write_bytes(contents)
    project = client.post("/api/projects", json={"name": "Review project"}).json()
    file = client.post(
        f"/api/projects/{project['id']}/files", json={"path": str(source)}
    ).json()
    client.put(
        f"/api/projects/{project['id']}/files/{file['id']}/format",
        json={"format_override": "text"},
    )
    output = tmp_path / f"clean-{name}"
    response = client.post(
        f"/api/projects/{project['id']}/files/{file['id']}/sanitize",
        json={"output_path": str(output)},
    )
    return response, project, file, output


def test_successful_sanitization_enters_persistent_review_queue_and_searches_only_output(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(_config())

    with BaseTestClient(app) as client:
        create_user("reviewer", "reviewer-password-123", ["operator", "reviewer"])
        login = client.post("/api/auth/login", json={
            "username": "reviewer", "password": "reviewer-password-123"
        })
        assert login.status_code == 200
        response, project, file, output = _sanitized_run(client, tmp_path)
        assert response.status_code == 200
        result = response.json()
        assert result["review_status"] == "pending_review"
        assert output.read_bytes() == b"REDACTED\n"

        queue = client.get("/api/reviews/queue")
        assert queue.status_code == 200
        run = next(item for item in queue.json() if item["id"] == result["review_run_id"])
        assert run["display_name"] == "app.log"
        assert run["output_name"] == "clean-app.log"
        assert "output_path" not in run
        assert str(tmp_path) not in str(run)

        matches = client.get(
            f"/api/reviews/runs/{run['id']}/search", params={"q": "REDACTED"}
        )
        assert matches.status_code == 200
        assert matches.json()["results"] == [{"line_number": 1, "snippet": "REDACTED"}]
        original_search = client.get(
            f"/api/reviews/runs/{run['id']}/search", params={"q": "secret=alpha"}
        )
        assert original_search.status_code == 200
        assert original_search.json()["match_count"] == 0

        saved = client.post("/api/reviews/saved-searches", json={
            "name": "Redactions", "query": "REDACTED"
        })
        assert saved.status_code == 201
        saved_id = saved.json()["id"]
        assert client.get("/api/reviews/saved-searches").json()[0]["id"] == saved_id
        saved_matches = client.get(
            f"/api/reviews/runs/{run['id']}/search",
            params={"saved_search_id": saved_id},
        )
        assert saved_matches.json()["match_count"] == 1

        # The audit database is durable and contains no output paths or log contents.
        audit_db = sqlite3.connect(tmp_path / "data" / "review.sqlite3")
        stored = audit_db.execute(
            "SELECT status, output_path FROM review_runs WHERE id=?",
            (run["id"],),
        ).fetchone()
        audit_db.close()
        assert stored[0] == "pending_review"
        assert stored[1] == str(output)
        assert client.get("/api/reviews/audit").status_code == 200


def test_review_requires_justified_exception_and_return_is_audited(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(_config())

    with BaseTestClient(app) as client:
        response, _, _, _ = _sanitized_run(client, tmp_path)
        run_id = response.json()["review_run_id"]

        invalid = client.post(
            f"/api/reviews/runs/{run_id}/approve",
            json={"exception": True, "comment": "Checked"},
        )
        assert invalid.status_code == 422
        assert client.get("/api/reviews/runs").json()[0]["status"] == "pending_review"

        returned = client.post(
            f"/api/reviews/runs/{run_id}/return",
            json={"comment": "Bitte Regel prüfen und erneut bereinigen."},
        )
        assert returned.status_code == 200
        assert returned.json()["status"] == "returned"
        assert returned.json()["last_comment"] == "Bitte Regel prüfen und erneut bereinigen."
        assert client.get("/api/reviews/queue").json() == []
        events = client.get("/api/reviews/audit").json()
        assert any(event["action"] == "return" and event["comment"] for event in events)


def test_review_exception_requires_reason_and_is_explicitly_audited(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(_config())

    with BaseTestClient(app) as client:
        response, _, _, _ = _sanitized_run(client, tmp_path)
        run_id = response.json()["review_run_id"]
        approved = client.post(
            f"/api/reviews/runs/{run_id}/approve",
            json={
                "exception": True,
                "exception_reason": "Manuell geprüft; dokumentierte fachliche Ausnahme.",
                "comment": "Freigabe mit Ausnahme.",
            },
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved_with_exception"
        events = client.get("/api/reviews/audit").json()
        event = next(item for item in events if item["action"] == "approve")
        assert event["exception_reason"] == "Manuell geprüft; dokumentierte fachliche Ausnahme."


def test_operator_without_reviewer_assignment_auto_approves_only_validated_run(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(_config())
    create_user("operator-only", "operator-password-123", ["operator"])

    with BaseTestClient(app) as client:
        login = client.post("/api/auth/login", json={
            "username": "operator-only", "password": "operator-password-123"
        })
        assert login.status_code == 200
        response, _, _, _ = _sanitized_run(client, tmp_path)
        assert response.status_code == 200
        assert response.json()["review_status"] == "approved"
        assert client.get("/api/reviews/runs").json()[0]["status"] == "approved"
        assert client.get("/api/reviews/queue").status_code == 403


def test_failed_sanitization_is_persisted_but_never_queued_for_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(_config())

    with BaseTestClient(app) as client:
        response, _, _, _ = _sanitized_run(
            client, tmp_path, name="invalid.log", contents=b"secret=alpha\ninvalid=\xff\n"
        )
        assert response.status_code == 422
        history = client.get("/api/reviews/runs", params={"status": "failed"})
        assert history.status_code == 200
        assert history.json()[0]["status"] == "failed"
        assert client.get("/api/reviews/queue").json() == []
