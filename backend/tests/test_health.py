from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_ok():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_healthz_sets_correlation_id_header():
    resp = client.get("/healthz")
    assert resp.headers.get("x-correlation-id")


def test_projects_requires_auth():
    resp = client.get("/projects")
    assert resp.status_code == 403  # no bearer credentials supplied


def test_project_sessions_requires_auth():
    # PRD §9.4 Session Browser feed — RLS-scoped, so unauthenticated is rejected.
    resp = client.get("/projects/00000000-0000-0000-0000-000000000000/sessions")
    assert resp.status_code == 403


def test_cluster_edit_requires_auth():
    # M7b editing endpoints are all behind require_user.
    resp = client.patch("/clusters/00000000-0000-0000-0000-000000000000", json={"name": "x"})
    assert resp.status_code == 403


def test_cluster_merge_requires_auth():
    resp = client.post("/clusters/merge", json={"survivor_id": "a", "merged_ids": ["b"]})
    assert resp.status_code == 403


def test_session_delete_requires_auth():
    resp = client.delete("/sessions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 403
