"""M8 — server-side role enforcement (PRD §10.3 / §11.2).

The backend's writes run as the service role (RLS-bypassing), so VA capability
restrictions can't lean on RLS — they're enforced in the API layer. These tests
drive the guards directly: an injected VA must be refused owner-only actions, and
the deep-mine cap / per-field restrictions must hold, all without touching the DB
(the owner-only guards short-circuit before any storage call; the in-handler
checks run against mocked storage).
"""

import pytest
from fastapi.testclient import TestClient

import app.api.sessions as sessions_api
from app.auth import AuthedUser, require_user
from app.main import app

_FAKE = AuthedUser(id="u-1", email="va@example.com", access_token="tok")


@pytest.fixture
def client():
    app.dependency_overrides[require_user] = lambda: _FAKE
    yield TestClient(app)
    app.dependency_overrides.clear()


def _as_role(monkeypatch, role: str):
    # require_owner (in app.auth.dependencies) resolves the role via get_role ->
    # ensure_user_profile; the in-handler checks call app.api.sessions.get_role.
    monkeypatch.setattr("app.auth.dependencies.ensure_user_profile", lambda *_: {"role": role})
    monkeypatch.setattr(sessions_api, "get_role", lambda _user: role)


# Owner-only endpoints: (method, path, json) tuples. Each must 403 for a VA at the
# dependency layer (no storage touched).
OWNER_ONLY = [
    ("delete", "/clusters/c1", None),
    ("post", "/clusters/merge", {"survivor_id": "a", "merged_ids": ["b"]}),
    ("post", "/clusters/c1/split", {"keyword_ids": ["k1"], "name": "n"}),
    ("post", "/clusters/c1/promote-primary", {"keyword_id": "k1"}),
    ("post", "/coverage-gaps/g1/accept", None),
    ("post", "/coverage-gaps/g1/dismiss", None),
    ("post", "/sessions/s1/architecture", None),
    ("delete", "/sessions/s1", None),
    ("post", "/sessions/s1/regate", {}),
    ("post", "/sessions/s1/cluster-preview", {}),
    ("post", "/sessions/s1/routing-diagnostic", {"probes": ["x"]}),
    ("post", "/sessions/s1/lever3-simulate", {}),
    ("post", "/sessions/s1/fanout", {}),
]


@pytest.mark.parametrize("method,path,body", OWNER_ONLY)
def test_owner_only_endpoints_forbidden_for_va(client, monkeypatch, method, path, body):
    _as_role(monkeypatch, "va")
    resp = client.request(method, path, json=body)
    assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"


def test_deep_mine_cap_enforced_for_va(client, monkeypatch):
    _as_role(monkeypatch, "va")
    topics = [{"id": f"t{i}"} for i in range(5)]
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user", lambda *_: {"id": "s1"})
    monkeypatch.setattr(sessions_api.store, "list_topics", lambda *_: topics)
    gated = {}
    monkeypatch.setattr(
        sessions_api.store, "set_topics_gating", lambda sid, ids: gated.update(ids=ids)
    )

    # seed + 3 silos exceeds the cap of 2 -> 400, nothing gated.
    over = client.post("/sessions/s1/deep-mine", json={"topic_ids": ["t0", "t1", "t2"]})
    assert over.status_code == 400
    assert "ids" not in gated

    # seed + 2 silos is allowed.
    ok = client.post("/sessions/s1/deep-mine", json={"topic_ids": ["t0", "t1"]})
    assert ok.status_code == 200
    assert gated["ids"] == ["t0", "t1"]


def test_owner_deep_mine_uncapped(client, monkeypatch):
    _as_role(monkeypatch, "owner")
    topics = [{"id": f"t{i}"} for i in range(5)]
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user", lambda *_: {"id": "s1"})
    monkeypatch.setattr(sessions_api.store, "list_topics", lambda *_: topics)
    monkeypatch.setattr(sessions_api.store, "set_topics_gating", lambda *_: None)
    resp = client.post("/sessions/s1/deep-mine", json={"topic_ids": ["t0", "t1", "t2", "t3"]})
    assert resp.status_code == 200


def test_va_cannot_edit_intent_or_h2(client, monkeypatch):
    _as_role(monkeypatch, "va")
    monkeypatch.setattr(sessions_api, "_require_cluster", lambda *_: ({"id": "c1"}, "s1"))
    assert client.patch("/clusters/c1", json={"intent": "commercial"}).status_code == 403
    assert client.patch("/clusters/c1", json={"suggested_h2s": ["a"]}).status_code == 403


def test_va_can_rename_cluster(client, monkeypatch):
    _as_role(monkeypatch, "va")
    monkeypatch.setattr(sessions_api, "_require_cluster", lambda *_: ({"id": "c1"}, "s1"))
    monkeypatch.setattr(sessions_api.store, "update_cluster", lambda cid, fields: {"id": cid, **fields})
    resp = client.patch("/clusters/c1", json={"name": "Renamed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"


def test_va_cannot_bulk_exclude(client, monkeypatch):
    _as_role(monkeypatch, "va")
    monkeypatch.setattr(sessions_api, "_require_session", lambda *_: {"id": "s1"})
    monkeypatch.setattr(sessions_api.store, "set_keywords_status", lambda *_: 1)
    assert (
        client.post("/sessions/s1/keywords/status", json={"keyword_ids": ["k1"], "status": "excluded"}).status_code
        == 403
    )
    # covered is allowed for VAs.
    assert (
        client.post("/sessions/s1/keywords/status", json={"keyword_ids": ["k1"], "status": "covered"}).status_code
        == 200
    )
