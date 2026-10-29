import sqlite3

from fastapi.testclient import TestClient as BaseTestClient
from test_client import TestClient

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
        client.headers.update({"X-CSRF-Token": client.cookies.get("logsanitizer_csrf")})
        response, _, _, output = _sanitized_run(client, tmp_path)
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

        create_user("second-reviewer", "second-reviewer-password-123", ["reviewer"])
        second_login = client.post("/api/auth/login", json={
            "username": "second-reviewer", "password": "second-reviewer-password-123"
        })
        assert second_login.status_code == 200
        client.headers.update({"X-CSRF-Token": client.cookies.get("logsanitizer_csrf")})
        assert client.get("/api/reviews/saved-searches").json() == []
        foreign_search = client.get(
            f"/api/reviews/runs/{run['id']}/search", params={"saved_search_id": saved_id}
        )
        assert foreign_search.status_code == 404

        # Replacing the output after validation must block both further sampling and approval.
        output.write_text("secret=alpha\\n", encoding="utf-8")
        changed_search = client.get(
            f"/api/reviews/runs/{run['id']}/search", params={"q": "secret"}
        )
        assert changed_search.status_code == 409
        changed_approval = client.post(
            f"/api/reviews/runs/{run['id']}/approve", json={"comment": "Must remain blocked"}
        )
        assert changed_approval.status_code == 409

        # The API omits paths; the private local database keeps the output path internally for verification.
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
    from logsanitizer import review_workflow
    notified = []
    monkeypatch.setattr(review_workflow, "notify_returned_run", lambda run: notified.append(run))

    with TestClient(app) as client:
        response, project, file, _ = _sanitized_run(client, tmp_path)
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
        assert len(notified) == 1
        assert notified[0]["id"] == run_id
        assert notified[0]["status"] == "returned"
        assert client.get("/api/reviews/queue").json() == []
        events = client.get("/api/reviews/audit").json()
        assert any(event["action"] == "return" and event["comment"] for event in events)

        retry_output = tmp_path / "reworked.log"
        retried = client.post(
            f"/api/projects/{project['id']}/files/{file['id']}/sanitize-jobs",
            json={"output_path": str(retry_output), "retry_of_run_id": run_id},
        )
        assert retried.status_code == 202
        assert retry_output.read_bytes() == b"REDACTED\n"
        latest = client.get("/api/reviews/runs").json()[0]
        assert latest["parent_run_id"] == run_id
        assert latest["status"] == "pending_review"


def test_review_exception_requires_reason_and_is_explicitly_audited(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(_config())

    with TestClient(app) as client:
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
        client.headers.update({"X-CSRF-Token": client.cookies.get("logsanitizer_csrf")})
        response, _, _, _ = _sanitized_run(client, tmp_path)
        assert response.status_code == 200
        assert response.json()["review_status"] == "approved"
        assert client.get("/api/reviews/runs").json()[0]["status"] == "approved"
        assert client.get("/api/reviews/queue").status_code == 403


def test_failed_sanitization_is_persisted_but_never_queued_for_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(_config())

    with TestClient(app) as client:
        response, _, _, _ = _sanitized_run(
            client, tmp_path, name="invalid.log", contents=b"secret=alpha\ninvalid=\xff\n"
        )
        assert response.status_code == 422
        history = client.get("/api/reviews/runs", params={"status": "failed"})
        assert history.status_code == 200
        assert history.json()[0]["status"] == "failed"
        assert client.get("/api/reviews/queue").json() == []


def test_review_search_bounds_results_and_shows_match_context(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(_config())

    with TestClient(app) as client:
        response, _, _, _ = _sanitized_run(
            client, tmp_path, contents=b"prefix-" + b"x" * 350 + b"secret=alpha-suffix\n" * 25
        )
        run_id = response.json()["review_run_id"]
        results = client.get(
            f"/api/reviews/runs/{run_id}/search", params={"q": "REDACTED"}
        )
        assert results.status_code == 200
        body = results.json()
        assert body["match_count"] == 20
        assert body["truncated"] is True
        assert len(body["results"]) == 20



def test_unknown_reviewer_assignment_fails_closed_and_records_pending_review(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(_config())

    from logsanitizer import review_workflow

    monkeypatch.setattr(review_workflow, "_review_assignee_state", lambda: None)
    with TestClient(app) as client:
        response, _, _, _ = _sanitized_run(client, tmp_path)
        assert response.status_code == 200
        assert response.json()["review_status"] == "pending_review"
        run_id = response.json()["review_run_id"]
        events = client.get("/api/reviews/audit").json()
        assert any(
            event["run_id"] == run_id and event["action"] == "pending_review"
            for event in events
        )


def test_reviewer_can_approve_and_stop_pending_runs_with_audit_events(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(_config())

    from logsanitizer import review_workflow

    monkeypatch.setattr(review_workflow, "_review_assignee_state", lambda: True)
    with TestClient(app) as client:
        approved_response, _, _, _ = _sanitized_run(
            client, tmp_path, name="approve.log"
        )
        stopped_response, _, _, _ = _sanitized_run(
            client, tmp_path, name="stop.log"
        )
        assert approved_response.status_code == 200
        assert stopped_response.status_code == 200
        approved_id = approved_response.json()["review_run_id"]
        stopped_id = stopped_response.json()["review_run_id"]

        approved = client.post(
            f"/api/reviews/runs/{approved_id}/approve",
            json={"comment": "Ausgabe stichprobenartig geprüft."},
        )
        stopped = client.post(
            f"/api/reviews/runs/{stopped_id}/stop",
            json={"comment": "Prüfung wegen fachlicher Unklarheit gestoppt."},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        assert stopped.status_code == 200
        assert stopped.json()["status"] == "stopped"

        events = client.get("/api/reviews/audit").json()
        assert any(
            event["run_id"] == approved_id
            and event["action"] == "approve"
            and event["comment"] == "Ausgabe stichprobenartig geprüft."
            for event in events
        )
        assert any(
            event["run_id"] == stopped_id
            and event["action"] == "stop"
            and event["comment"] == "Prüfung wegen fachlicher Unklarheit gestoppt."
            for event in events
        )


def test_operator_cannot_access_review_decisions_search_comments_or_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSANITIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGSANITIZER_RULES_DIR", str(tmp_path / "rules"))
    save_rule_config(_config())
    create_user("operator-review-boundary", "operator-password-456", ["operator"])
    create_user("assigned-reviewer", "reviewer-password-456", ["reviewer"])

    with BaseTestClient(app) as client:
        login = client.post("/api/auth/login", json={
            "username": "operator-review-boundary",
            "password": "operator-password-456",
        })
        assert login.status_code == 200
        client.headers.update({
            "X-CSRF-Token": client.cookies.get("logsanitizer_csrf")
        })
        response, _, _, _ = _sanitized_run(client, tmp_path)
        assert response.status_code == 200
        run_id = response.json()["review_run_id"]
        assert response.json()["review_status"] == "pending_review"

        denied = [
            client.get("/api/reviews/queue"),
            client.get("/api/reviews/audit"),
            client.get("/api/reviews/saved-searches"),
            client.get(f"/api/reviews/runs/{run_id}/search", params={"q": "REDACTED"}),
            client.post("/api/reviews/saved-searches", json={
                "name": "Operator search", "query": "REDACTED"
            }),
            client.post(f"/api/reviews/runs/{run_id}/approve", json={}),
            client.post(f"/api/reviews/runs/{run_id}/return", json={
                "comment": "Operator must not return a run."
            }),
            client.post(f"/api/reviews/runs/{run_id}/stop", json={}),
            client.post(f"/api/reviews/runs/{run_id}/comments", json={
                "comment": "Operator must not comment."
            }),
        ]
        assert [item.status_code for item in denied] == [403] * len(denied)
        assert client.get("/api/reviews/runs").status_code == 200
        assert client.get("/api/reviews/runs").json()[0]["status"] == "pending_review"
