"""Cooperative cancellation: registry semantics, the /cancel endpoint, and the
cancel-check in the external-API call sites. No DB; the endpoint test mocks
storage like test_roles.py."""

import threading

import pytest
from fastapi.testclient import TestClient

import app.api.sessions as sessions_api
from app import cancellation
from app.auth import AuthedUser, require_user
from app.cancellation import (
    CancelledByUser,
    clear,
    is_cancelled,
    raise_if_cancelled,
    register,
    set_cancelled,
)
from app.logging import bind_session_id
from app.main import app

_FAKE = AuthedUser(id="u-1", email="user@example.com", access_token="tok")


@pytest.fixture
def client():
    app.dependency_overrides[require_user] = lambda: _FAKE
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_cancellation_registry():
    cancellation._events.clear()
    yield
    cancellation._events.clear()


# ---------------------------------------------------------------------------
# Registry semantics
# ---------------------------------------------------------------------------
def test_register_creates_event_and_is_idempotent():
    a = register("s-1")
    b = register("s-1")
    assert a is b
    assert isinstance(a, threading.Event)
    assert not a.is_set()


def test_set_cancelled_makes_is_cancelled_true():
    register("s-1")
    assert not is_cancelled("s-1")
    set_cancelled("s-1")
    assert is_cancelled("s-1")


def test_set_cancelled_before_register_is_picked_up_by_register():
    """A /cancel that lands before the worker thread enters its job must still be
    visible — register adopts the pre-set event rather than creating a fresh one."""
    set_cancelled("s-1")
    evt = register("s-1")
    assert evt.is_set()
    assert is_cancelled("s-1")


def test_clear_drops_event_for_next_run():
    set_cancelled("s-1")
    clear("s-1")
    assert not is_cancelled("s-1")
    # And a fresh register on the same id starts unset.
    assert not register("s-1").is_set()


def test_raise_if_cancelled_reads_contextvar(monkeypatch):
    bind_session_id("s-1")
    register("s-1")
    raise_if_cancelled()  # not set: no raise
    set_cancelled("s-1")
    with pytest.raises(CancelledByUser):
        raise_if_cancelled()


def test_raise_if_cancelled_noop_when_no_session_bound():
    bind_session_id(None)
    set_cancelled("s-1")  # set on a different (no) session — irrelevant
    # Without a bound session_id, raise_if_cancelled is a no-op (used by callers
    # that legitimately run outside any pipeline run).
    raise_if_cancelled()


# ---------------------------------------------------------------------------
# /cancel endpoint
# ---------------------------------------------------------------------------
def test_cancel_endpoint_flips_status_and_signals_worker(client, monkeypatch):
    monkeypatch.setattr(
        sessions_api.store, "session_visible_to_user", lambda *_: {"id": "s1"}
    )
    flipped: dict = {}

    def fake_try_mark_cancelled(sid: str) -> bool:
        flipped["sid"] = sid
        return True

    monkeypatch.setattr(sessions_api.store, "try_mark_cancelled", fake_try_mark_cancelled)
    resp = client.post("/sessions/s1/cancel")
    assert resp.status_code == 200
    assert resp.json() == {"status": "cancelled", "session_id": "s1"}
    assert flipped["sid"] == "s1"
    # Worker signalled via the registry — a hot loop will now raise on next check.
    assert is_cancelled("s1")


def test_cancel_endpoint_returns_409_when_not_running(client, monkeypatch):
    monkeypatch.setattr(
        sessions_api.store, "session_visible_to_user", lambda *_: {"id": "s1"}
    )
    monkeypatch.setattr(sessions_api.store, "try_mark_cancelled", lambda sid: False)
    resp = client.post("/sessions/s1/cancel")
    assert resp.status_code == 409
    # Registry not touched on a 409 — nothing to signal.
    assert not is_cancelled("s1")


def test_cancel_endpoint_404_when_session_not_visible(client, monkeypatch):
    monkeypatch.setattr(sessions_api.store, "session_visible_to_user", lambda *_: None)
    resp = client.post("/sessions/s1/cancel")
    assert resp.status_code == 404
    assert not is_cancelled("s1")


def test_cancel_endpoint_allowed_for_va(client, monkeypatch):
    """A VA can cancel their own session — capability matrix §11.2 'VA can manage
    own sessions'. RLS already restricts session_visible_to_user to sessions the
    caller owns, so the endpoint itself doesn't gate on role."""
    monkeypatch.setattr("app.auth.dependencies.ensure_user_profile", lambda *_: {"role": "va"})
    monkeypatch.setattr(sessions_api, "get_role", lambda _user: "va")
    monkeypatch.setattr(
        sessions_api.store, "session_visible_to_user", lambda *_: {"id": "s1"}
    )
    monkeypatch.setattr(sessions_api.store, "try_mark_cancelled", lambda sid: True)
    resp = client.post("/sessions/s1/cancel")
    assert resp.status_code == 200
