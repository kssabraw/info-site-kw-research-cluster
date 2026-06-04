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
        lambda *_: session if session is not None
        else {"id": "s1", "seed_keyword": "retatrutide"},
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
                        lambda path, ttl, download_name=None:
                        calls["sign"].append((path, ttl, download_name)) or "https://signed/url")
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
    # The signed URL is stamped with a seed-based attachment filename so the
    # user's downloads folder shows e.g. retatrutide-flat.csv (not the opaque
    # fanout-flat.csv we used pre-personalization).
    assert calls["sign"][0][2] == "retatrutide-flat.csv"


def test_create_cleans_up_object_when_insert_fails(client, monkeypatch):
    # If recording the export row fails after the upload, the orphan object is
    # removed from Storage and the error propagates (no silent partial state).
    _visible(monkeypatch)
    _stub_flat_data(monkeypatch)
    calls = _capture_storage(monkeypatch)
    removed = {}
    monkeypatch.setattr(exports_api.export_store, "insert_export",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr(exports_api.export_store, "remove_object",
                        lambda path: removed.update(path=path))
    with pytest.raises(RuntimeError):
        client.post("/sessions/s1/export?format=flat")
    assert removed["path"] == calls["upload"][0][0]  # the uploaded object was cleaned up


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
    # Re-download refetches the session for the seed-based download name.
    _visible(monkeypatch)
    signed = {}
    monkeypatch.setattr(exports_api.export_store, "create_signed_url",
                        lambda path, ttl, download_name=None:
                        signed.update(path=path, name=download_name) or "https://fresh/url")
    r = client.get("/exports/e1/download")
    assert r.status_code == 200
    assert r.json()["download_url"] == "https://fresh/url"
    assert signed["path"] == "u-1/s1/x.csv"
    assert signed["name"] == "retatrutide-flat.csv"


def test_download_falls_back_to_fanout_slug_when_session_missing(client, monkeypatch):
    # Race: the export row is visible but the parent session was deleted between
    # list and download. Filename falls back to "fanout-…" rather than 500.
    monkeypatch.setattr(exports_api.export_store, "get_export_visible",
                        lambda token, eid: {"id": eid, "session_id": "s1", "format": "flat",
                                            "storage_path": "p", "generated_at": "t"})
    _visible(monkeypatch, session=False)
    signed = {}
    monkeypatch.setattr(exports_api.export_store, "create_signed_url",
                        lambda path, ttl, download_name=None:
                        signed.update(name=download_name) or "https://fresh/url")
    r = client.get("/exports/e1/download")
    assert r.status_code == 200
    assert signed["name"] == "fanout-flat.csv"


def test_download_not_visible_404(client, monkeypatch):
    monkeypatch.setattr(exports_api.export_store, "get_export_visible", lambda token, eid: None)
    assert client.get("/exports/e1/download").status_code == 404


# ---- export-selected (§9.1 bulk action) ----------------------------------
def _stub_topics_and_clusters(monkeypatch):
    monkeypatch.setattr(exports_api.store, "list_topics",
                        lambda *_: [{"id": "t1", "name": "Mechanism"}])
    monkeypatch.setattr(exports_api.store, "list_clusters",
                        lambda *_: [{"id": "c1", "name": "Half-life"}])


def test_export_selected_streams_flat_csv_for_selected_ids(client, monkeypatch):
    """Happy path: rows resolve, the response is a CSV body with attachment
    headers, and only the selected ids drive the SQL — not the surviving pool."""
    _visible(monkeypatch)
    _stub_topics_and_clusters(monkeypatch)
    captured: dict = {}

    def fake_by_ids(sid, ids):
        captured["sid"] = sid
        captured["ids"] = list(ids)
        return [
            {"keyword": "ozempic alternatives", "topic_id": "t1", "cluster_id": "c1",
             "sources": ["competitor"], "status": "active", "relevance_score": 0.71,
             "volume": 22000, "cpc_usd": 4.5,
             "keyword_difficulty": 71.0, "competition_index": 0.34},
            {"keyword": "ozempic dose", "topic_id": "t1", "cluster_id": None,
             "sources": ["ki"], "status": "covered", "relevance_score": 0.83,
             "volume": 8100, "cpc_usd": 2.1,
             "keyword_difficulty": 55.0, "competition_index": 0.21},
        ]

    monkeypatch.setattr(exports_api.store, "list_keywords_by_ids", fake_by_ids)

    r = client.post("/sessions/s1/export-selected", json={"keyword_ids": ["k1", "k2"]})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    cd = r.headers["content-disposition"]
    assert cd.startswith("attachment;") and cd.endswith('.csv"')
    # Filename is seed-slugged so the download lands as e.g.
    # retatrutide-selected-…csv in the user's downloads folder.
    assert 'filename="retatrutide-selected-' in cd
    assert r.headers["cache-control"] == "no-store"
    # Only the requested ids are passed to the storage helper.
    assert captured == {"sid": "s1", "ids": ["k1", "k2"]}
    body = r.content.decode("utf-8")
    # Header line first, two data rows after.
    lines = body.strip().splitlines()
    assert "keyword" in lines[0] and "volume" in lines[0] and "cpc" in lines[0]
    assert "ozempic alternatives" in body
    assert "22000" in body  # volume rendered
    # Cluster id resolved to the cluster *name*.
    assert "Half-life" in body
    # Topic id resolved to the topic name.
    assert "Mechanism" in body


def test_export_selected_400_when_none_resolve(client, monkeypatch):
    """A stale UI selection (e.g. after a re-gate) where no ids resolve should
    surface a clear 400 rather than hand back a header-only CSV."""
    _visible(monkeypatch)
    _stub_topics_and_clusters(monkeypatch)
    monkeypatch.setattr(exports_api.store, "list_keywords_by_ids", lambda *_: [])
    r = client.post("/sessions/s1/export-selected", json={"keyword_ids": ["ghost"]})
    assert r.status_code == 400
    assert "Refresh" in r.json()["detail"]


def test_export_selected_404_when_session_not_visible(client, monkeypatch):
    """RLS-scoped: the session-visibility check fires before any DB read."""
    _visible(monkeypatch, session=False)
    r = client.post("/sessions/s1/export-selected", json={"keyword_ids": ["k1"]})
    assert r.status_code == 404


# ---- download-name slug rules --------------------------------------------
def test_slug_seed_lowercases_and_hyphenates_punctuation():
    # Common seed shapes: spaces, casing, trailing punctuation, mixed alnum.
    assert exports_api._slug_seed("Managed Service Provider") == "managed-service-provider"
    assert exports_api._slug_seed("cyber security") == "cyber-security"
    assert exports_api._slug_seed("AI agents 2026!") == "ai-agents-2026"
    assert exports_api._slug_seed("  whitespace  ") == "whitespace"


def test_slug_seed_collapses_repeated_separators():
    assert exports_api._slug_seed("a//b   c—d") == "a-b-c-d"
    assert exports_api._slug_seed("--leading and trailing--") == "leading-and-trailing"


def test_slug_seed_falls_back_for_empty_or_pure_punct():
    assert exports_api._slug_seed(None) == "fanout"
    assert exports_api._slug_seed("") == "fanout"
    assert exports_api._slug_seed("???") == "fanout"
    assert exports_api._slug_seed("   ") == "fanout"


def test_slug_seed_caps_length_at_80_chars():
    long_seed = "a" * 200
    slug = exports_api._slug_seed(long_seed)
    assert len(slug) <= 80
    assert slug == "a" * 80


def test_download_filename_format_matches_seed_and_format():
    assert exports_api._download_filename("flat", "retatrutide") == "retatrutide-flat.csv"
    assert (
        exports_api._download_filename("topic_grouped", "cyber security")
        == "cyber-security-topic_grouped.zip"
    )
    assert exports_api._download_filename("architecture", None) == "fanout-architecture.csv"


def test_export_selected_requires_at_least_one_id(client, monkeypatch):
    """An empty selection is a client bug (the bulk bar gates the button), so
    422 from pydantic min_length is the right answer — not a silent header-only
    CSV."""
    _visible(monkeypatch)
    r = client.post("/sessions/s1/export-selected", json={"keyword_ids": []})
    assert r.status_code == 422


def test_export_selected_caps_request_size(client, monkeypatch):
    """10k ids is the documented cap; one more is 422."""
    _visible(monkeypatch)
    r = client.post(
        "/sessions/s1/export-selected",
        json={"keyword_ids": [f"k{i}" for i in range(10_001)]},
    )
    assert r.status_code == 422


def test_export_selected_available_to_va(client, monkeypatch):
    """Export is ✓ for both roles (§11.2); a VA can run this on their own
    visible session."""
    monkeypatch.setattr("app.auth.dependencies.ensure_user_profile", lambda *_: {"role": "va"})
    _visible(monkeypatch)
    _stub_topics_and_clusters(monkeypatch)
    monkeypatch.setattr(
        exports_api.store, "list_keywords_by_ids",
        lambda sid, ids: [{"keyword": "k", "topic_id": "t1", "cluster_id": None,
                           "sources": [], "status": "active", "relevance_score": 0.6,
                           "volume": None, "cpc_usd": None,
                           "keyword_difficulty": None, "competition_index": None}],
    )
    r = client.post("/sessions/s1/export-selected", json={"keyword_ids": ["k1"]})
    assert r.status_code == 200
