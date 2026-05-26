"""M10 — CSV export endpoints (PRD §12).

Drive create / list / re-download against mocked storage (no DB, no Storage
egress), asserting: both roles can export (it's not owner-only, §11.2), session
visibility is enforced, format validation, the architecture-missing 400, and
that create uploads + records + signs exactly once."""

import pytest
from fastapi.testclient import TestClient

import app.api.exports as exports_api
from app.auth import AuthedUser, require_user
from app.main import app

_USER = AuthedUser(id="u-1", email="who@example.com", access_token="tok")


@pytest.fixture
def client():
    app.dependency_overrides[require_user] = lambda: _USER
    yield TestClient(app)
    app.dependency_overrides.clear()


def _visible(monkeypatch, session=None):
    monkeypatch.setattr(
        exports_api.store, "session_visible_to_user",
        lambda *_: session if session is not None else {"id": "s1"},
    )


def _stub_flat_data(monkeypatch):
    monkeypatch.setattr(exports_api.store, "list_topics", lambda *_: [{"id": "t1", "name": "M"}])
    monkeypatch.setattr(exports_api.store, "list_surviving_keywords",
                        lambda *_: [{"keyword": "k", "topic_id": "t1", "cluster_id": None,
                                     "sources": [], "status": "active", "relevance_score": 0.7}])
    monkeypatch.setattr(exports_api.store, "list_clusters", lambda *_: [])


def _capture_storage(monkeypatch):
    calls = {"upload": [], "insert": [], "sign": []}
    monkeypatch.setattr(exports_api.export_store, "upload_snapshot",
                        lambda path, data, ct: calls["upload"].append((path, len(data), ct)))
    monkeypatch.setattr(exports_api.export_store, "insert_export",
                        lambda sid, uid, fmt, path: calls["insert"].append((sid, uid, fmt, path))
                        or {"id": "e1", "generated_at": "2026-05-28T00:00:00Z"})
    monkeypatch.setattr(exports_api.export_store, "create_signed_url",
                        lambda path, ttl: calls["sign"].append((path, ttl)) or "https://signed/url")
    return calls


# ---- create ---------------------------------------------------------------
def test_create_flat_export_uploads_records_and_signs(client, monkeypatch):
    _visible(monkeypatch)
    _stub_flat_data(monkeypatch)
    calls = _capture_storage(monkeypatch)
    r = client.post("/sessions/s1/export?format=flat")
    assert r.status_code == 200
    body = r.json()
    assert body["export_id"] == "e1"
    assert body["download_url"] == "https://signed/url"
    assert body["format"] == "flat"
    assert len(calls["upload"]) == 1
    assert calls["upload"][0][2] == "text/csv"
    assert calls["upload"][0][0].startswith("u-1/s1/")  # {user}/{session}/...
    assert calls["insert"][0] == ("s1", "u-1", "flat", body["storage_path"])
    assert len(calls["sign"]) == 1


def test_create_topic_grouped_is_zip(client, monkeypatch):
    _visible(monkeypatch)
    _stub_flat_data(monkeypatch)
    calls = _capture_storage(monkeypatch)
    r = client.post("/sessions/s1/export?format=topic_grouped")
    assert r.status_code == 200
    assert calls["upload"][0][2] == "application/zip"
    assert calls["upload"][0][0].endswith(".zip")


def test_create_architecture_requires_generated_architecture(client, monkeypatch):
    _visible(monkeypatch)
    monkeypatch.setattr(exports_api.store, "list_topics", lambda *_: [])
    monkeypatch.setattr(exports_api.store, "get_architecture", lambda *_: None)
    _capture_storage(monkeypatch)
    r = client.post("/sessions/s1/export?format=architecture")
    assert r.status_code == 400


def test_create_architecture_ok(client, monkeypatch):
    _visible(monkeypatch)
    monkeypatch.setattr(exports_api.store, "list_topics", lambda *_: [{"id": "t1", "name": "M"}])
    monkeypatch.setattr(exports_api.store, "get_architecture",
                        lambda *_: {"architecture_json": {"pillars": [
                            {"topic_id": "t1", "title": "T", "target_keyword": "tk",
                             "h2_outline": [], "supporting_article_ids": [],
                             "lateral_pillar_links": []}], "supporting_articles": []}})
    monkeypatch.setattr(exports_api.store, "list_clusters", lambda *_: [])
    monkeypatch.setattr(exports_api.store, "get_keyword_texts", lambda *_: {})
    calls = _capture_storage(monkeypatch)
    r = client.post("/sessions/s1/export?format=architecture")
    assert r.status_code == 200
    assert calls["upload"][0][2] == "text/csv"


def test_create_invalid_format(client, monkeypatch):
    _visible(monkeypatch)
    assert client.post("/sessions/s1/export?format=bogus").status_code == 400


def test_create_missing_format(client, monkeypatch):
    _visible(monkeypatch)
    # `format` is a required query param -> 422 from FastAPI validation.
    assert client.post("/sessions/s1/export").status_code == 422


def test_create_export_session_not_visible_404(client, monkeypatch):
    _visible(monkeypatch, session=False)
    assert client.post("/sessions/s1/export?format=flat").status_code == 404


def test_export_available_to_va(client, monkeypatch):
    # Export is ✓ for VAs (§11.2): no owner gate. A VA exporting their own visible
    # session succeeds (require_user only).
    monkeypatch.setattr("app.auth.dependencies.ensure_user_profile", lambda *_: {"role": "va"})
    _visible(monkeypatch)
    _stub_flat_data(monkeypatch)
    _capture_storage(monkeypatch)
    assert client.post("/sessions/s1/export?format=flat").status_code == 200


# ---- list / download ------------------------------------------------------
def test_list_exports_scoped_to_session(client, monkeypatch):
    _visible(monkeypatch)
    monkeypatch.setattr(exports_api.export_store, "list_exports",
                        lambda token, sid: [{"id": "e1", "session_id": sid, "format": "flat",
                                             "storage_path": "p", "generated_at": "t"}])
    r = client.get("/sessions/s1/exports")
    assert r.status_code == 200
    assert r.json()[0]["id"] == "e1"


def test_download_reissues_fresh_signed_url(client, monkeypatch):
    monkeypatch.setattr(exports_api.export_store, "get_export_visible",
                        lambda token, eid: {"id": eid, "session_id": "s1", "format": "flat",
                                            "storage_path": "u-1/s1/x.csv", "generated_at": "t"})
    signed = {}
    monkeypatch.setattr(exports_api.export_store, "create_signed_url",
                        lambda path, ttl: signed.update(path=path) or "https://fresh/url")
    r = client.get("/exports/e1/download")
    assert r.status_code == 200
    assert r.json()["download_url"] == "https://fresh/url"
    assert signed["path"] == "u-1/s1/x.csv"


def test_download_not_visible_404(client, monkeypatch):
    monkeypatch.setattr(exports_api.export_store, "get_export_visible", lambda token, eid: None)
    assert client.get("/exports/e1/download").status_code == 404
