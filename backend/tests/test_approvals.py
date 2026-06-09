"""M9 — approval workflow endpoints (PRD §11.3).

Drive the submit -> approve / reject / cancel flow against mocked storage (no DB,
no egress), asserting the owner-only gates (§11.2), the status transitions, and
that approve kicks the pipeline exactly once."""

import pytest
from fastapi.testclient import TestClient

import app.api.sessions as sessions_api
from app.auth import require_user
from app.auth import AuthedUser
from app.main import app

_USER = AuthedUser(id="u-1", email="who@example.com", access_token="tok")


@pytest.fixture
def client():
    app.dependency_overrides[require_user] = lambda: _USER
    yield TestClient(app)
    app.dependency_overrides.clear()


def _as_role(monkeypatch, role: str):
    monkeypatch.setattr("app.auth.dependencies.ensure_user_profile", lambda *_: {"role": role})
    monkeypatch.setattr(sessions_api, "get_role", lambda _user: role)


def _mock_estimate_deps(monkeypatch, gated=2, silos=5):
    monkeypatch.setattr(sessions_api.store, "list_topics",
                        lambda *_: [{"id": f"t{i}"} for i in range(silos)])
    monkeypatch.setattr(sessions_api.store, "count_gated_topics", lambda *_: gated)
    monkeypatch.setattr(sessions_api.store, "get_workspace_settings",
                        lambda: {"va_soft_cap_usd": 5.00})


# ---- owner-only gates -----------------------------------------------------
OWNER_ONLY = [
    ("get", "/approvals", None),
    ("post", "/sessions/s1/approve", {}),
    ("post", "/sessions/s1/reject", {}),
]


@pytest.mark.parametrize("method,path,body", OWNER_ONLY)
def test_approval_admin_endpoints_forbidden_for_va(client, monkeypatch, method, path, body):
    _as_role(monkeypatch, "va")
    assert client.request(method, path, json=body).status_code == 403


# ---- cost estimate --------------------------------------------------------
def test_cost_estimate_reports_gate(client, monkeypatch):
    _as_role(monkeypatch, "va")
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user",
                        lambda *_: {"id": "s1", "settings": {"coverage_mode": "standard"}})
    _mock_estimate_deps(monkeypatch, gated=2, silos=5)
    r = client.get("/sessions/s1/cost-estimate?gated_count=2")
    assert r.status_code == 200
    body = r.json()
    assert body["estimated_cost_usd"] > 0
    assert body["requires_approval"] is False  # standard 5-silo run is under cap


# ---- submit / cancel ------------------------------------------------------
def test_submit_for_approval_sets_pending(client, monkeypatch):
    _as_role(monkeypatch, "va")
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user",
                        lambda *_: {"id": "s1", "status": "awaiting_silo_review",
                                    "settings": {"coverage_mode": "comprehensive"}})
    _mock_estimate_deps(monkeypatch, gated=2, silos=5)
    captured = {}
    monkeypatch.setattr(sessions_api.store, "update_session",
                        lambda sid, fields: captured.update(fields) or {"id": sid})
    r = client.post("/sessions/s1/submit-for-approval")
    assert r.status_code == 200
    assert captured["status"] == "pending_approval"
    assert captured["approval_required"] is True
    assert captured["estimated_cost_usd"] > 0
    # A resubmission must clear any prior decision.
    assert captured["approval_decided_by_user_id"] is None


def test_submit_for_approval_rejected_from_wrong_status(client, monkeypatch):
    _as_role(monkeypatch, "va")
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user",
                        lambda *_: {"id": "s1", "status": "complete", "settings": {}})
    assert client.post("/sessions/s1/submit-for-approval").status_code == 409


def test_resubmit_allowed_from_rejected(client, monkeypatch):
    _as_role(monkeypatch, "va")
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user",
                        lambda *_: {"id": "s1", "status": "rejected",
                                    "settings": {"coverage_mode": "standard"}})
    _mock_estimate_deps(monkeypatch)
    monkeypatch.setattr(sessions_api.store, "update_session", lambda sid, fields: {"id": sid})
    assert client.post("/sessions/s1/submit-for-approval").status_code == 200


def test_cancel_approval_returns_to_review(client, monkeypatch):
    _as_role(monkeypatch, "va")
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user",
                        lambda *_: {"id": "s1", "status": "pending_approval", "settings": {}})
    captured = {}
    monkeypatch.setattr(sessions_api.store, "update_session",
                        lambda sid, fields: captured.update(fields) or {"id": sid})
    r = client.post("/sessions/s1/cancel-approval")
    assert r.status_code == 200
    assert captured["status"] == "awaiting_silo_review"
    assert captured["approval_required"] is False


def test_cancel_approval_wrong_status(client, monkeypatch):
    _as_role(monkeypatch, "va")
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user",
                        lambda *_: {"id": "s1", "status": "running", "settings": {}})
    assert client.post("/sessions/s1/cancel-approval").status_code == 409


# ---- approve / reject -----------------------------------------------------
def test_approve_kicks_pipeline(client, monkeypatch):
    _as_role(monkeypatch, "owner")
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user",
                        lambda *_: {"id": "s1", "status": "pending_approval", "settings": {}})
    monkeypatch.setattr(sessions_api.store, "list_topics", lambda *_: [{"id": "t0"}])
    monkeypatch.setattr(sessions_api.store, "try_mark_running", lambda *_: True)
    captured = {}
    monkeypatch.setattr(sessions_api.store, "update_session",
                        lambda sid, fields: captured.update(fields) or {"id": sid})
    submitted = {}
    monkeypatch.setattr(sessions_api.jobs, "submit_expand",
                        lambda sid: submitted.update(sid=sid))
    r = client.post("/sessions/s1/approve", json={"note": "looks good"})
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert submitted["sid"] == "s1"
    assert captured["approval_decided_by_user_id"] == "u-1"
    assert captured["approval_note"] == "looks good"
    assert captured["approval_decision_at"]


def test_approve_wrong_status_does_not_run(client, monkeypatch):
    _as_role(monkeypatch, "owner")
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user",
                        lambda *_: {"id": "s1", "status": "awaiting_silo_review", "settings": {}})
    called = {}
    monkeypatch.setattr(sessions_api.jobs, "submit_expand",
                        lambda sid: called.update(sid=sid))
    assert client.post("/sessions/s1/approve", json={}).status_code == 409
    assert "sid" not in called


def test_expand_blocks_over_cap_va(client, monkeypatch):
    # A VA cannot bypass the gate by calling /expand directly on an over-cap run.
    _as_role(monkeypatch, "va")
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user",
                        lambda *_: {"id": "s1", "settings": {"coverage_mode": "comprehensive"}})
    monkeypatch.setattr(sessions_api.store, "list_topics",
                        lambda *_: [{"id": f"t{i}"} for i in range(10)])
    monkeypatch.setattr(sessions_api.store, "count_gated_topics", lambda *_: 2)
    # Soft cap lowered so this comprehensive run is unambiguously over it.
    monkeypatch.setattr(sessions_api.store, "get_workspace_settings",
                        lambda: {"va_soft_cap_usd": 2.00})
    marked = {}
    monkeypatch.setattr(sessions_api.store, "try_mark_running",
                        lambda sid: marked.update(sid=sid) or True)
    r = client.post("/sessions/s1/expand")
    assert r.status_code == 403
    assert "sid" not in marked  # never claimed the run


def test_expand_allows_under_cap_va(client, monkeypatch):
    _as_role(monkeypatch, "va")
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user",
                        lambda *_: {"id": "s1", "settings": {"coverage_mode": "standard"}})
    monkeypatch.setattr(sessions_api.store, "list_topics",
                        lambda *_: [{"id": f"t{i}"} for i in range(4)])
    monkeypatch.setattr(sessions_api.store, "count_gated_topics", lambda *_: 1)
    monkeypatch.setattr(sessions_api.store, "get_workspace_settings",
                        lambda: {"va_soft_cap_usd": 5.00})
    monkeypatch.setattr(sessions_api.store, "try_mark_running", lambda *_: True)
    monkeypatch.setattr(sessions_api.jobs, "submit_expand", lambda *_: None)
    # The estimate is persisted at run-start so the cost banner has it (PRD §8.4).
    persisted = {}
    monkeypatch.setattr(sessions_api.store, "update_session",
                        lambda sid, fields: persisted.update(fields) or {"id": sid})
    assert client.post("/sessions/s1/expand").status_code == 202
    assert persisted["estimated_cost_usd"] > 0


def test_reject_sets_rejected_with_note(client, monkeypatch):
    _as_role(monkeypatch, "owner")
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user",
                        lambda *_: {"id": "s1", "status": "pending_approval", "settings": {}})
    captured = {}
    monkeypatch.setattr(sessions_api.store, "update_session",
                        lambda sid, fields: captured.update(fields) or {"id": sid})
    submitted = {}
    monkeypatch.setattr(sessions_api.jobs, "submit_expand",
                        lambda sid: submitted.update(sid=sid))
    r = client.post("/sessions/s1/reject", json={"note": "too expensive, drop a silo"})
    assert r.status_code == 200
    assert captured["status"] == "rejected"
    assert captured["approval_note"] == "too expensive, drop a silo"
    assert "sid" not in submitted  # pipeline never started
