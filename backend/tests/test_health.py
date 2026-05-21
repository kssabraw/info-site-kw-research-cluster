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
