"""Demo companion page endpoints (PRD §6.12, D-52)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from siege import main
from siege.events import bus


@pytest.fixture
def client(isolated_runs_dir, monkeypatch):
    monkeypatch.setattr(main, "RUNS_DIR", isolated_runs_dir)
    main._last_send_by_ip.clear()
    main._sent_pairs.clear()
    return TestClient(main.app)


def test_current_run_is_idle_with_nothing_recorded(client):
    resp = client.get("/api/runs/current")
    assert resp.status_code == 200
    assert resp.json() == {"status": "idle", "run_id": None, "report": None}


def test_current_run_reports_a_live_channel(client):
    bus.create("run_demo_live", persist=False)
    try:
        resp = client.get("/api/runs/current")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "live"
        assert body["run_id"] == "run_demo_live"
        assert body["report"] is None
    finally:
        bus.drop("run_demo_live")


def test_email_rejects_unfinished_run(client):
    resp = client.post("/api/runs/does-not-exist/email", json={"email": "judge@example.com"})
    assert resp.status_code == 404


def test_email_rejects_malformed_address(client):
    bus.create("run_demo_bad_email", persist=False)
    bus.drop("run_demo_bad_email")
    resp = client.post("/api/runs/run_demo_bad_email/email", json={"email": "not-an-email"})
    assert resp.status_code in (400, 404)  # bad format short-circuits before the report lookup


def test_email_rate_limits_repeat_submissions(client, monkeypatch):
    from siege.orchestrator import _persist
    from siege.schemas import Report

    report = Report(run_id="run_demo_finished", model="test-model", provider="fake")
    _persist(report)

    monkeypatch.setattr(main, "send_report_email", lambda *a, **k: None)

    first = client.post("/api/runs/run_demo_finished/email", json={"email": "judge@example.com"})
    assert first.status_code == 200
    assert first.json()["ok"] is True

    second = client.post("/api/runs/run_demo_finished/email", json={"email": "another@example.com"})
    assert second.status_code == 429


def test_leaderboard_includes_started_at(client):
    from siege.orchestrator import _persist
    from siege.schemas import Report

    report = Report(run_id="run_lb_test", model="test-lb-model", provider="test-provider", trust_score=85.0)
    _persist(report)

    resp = client.get("/api/leaderboard")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    found = next((r for r in rows if r["run_id"] == "run_lb_test"), None)
    assert found is not None
    assert found["model"] == "test-lb-model"
    assert found["started_at"] is not None


def test_a_crashed_run_does_not_stay_live_forever(client, monkeypatch):
    """A run that raised never reached `channel.close()`, so `/api/runs/current`
    kept sending every /demo viewer to that dead run."""
    def boom(req, channel, backend):
        raise RuntimeError("LocalStack went away")

    monkeypatch.setattr(main, "execute_run", boom)
    channel = bus.create("run_demo_crash", persist=False)
    main._execute_run_safely(main.RunRequest(model="m", provider="groq"), channel)

    assert channel.closed
    assert "run_demo_crash" not in bus.active_ids()
    assert client.get("/api/runs/current").json()["status"] != "live"
    assert any(e.type == "run.error" and "LocalStack went away" in e.data["message"]
               for e in channel.buffer)
