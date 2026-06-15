"""Freeze-old-sessions guard (2026-06-15 OpenAI->Gemini embeddings swap).

A session whose stored vectors were built with a different embedding model than the
active one must not be re-processed — text-embedding-3-small and gemini-embedding-001
are both 1536-dim but live in different spaces, so re-embedding would silently mix
them. The guard is a no-op during the dormant period (active == OpenAI).
"""

import types

import pytest
from fastapi import HTTPException

import app.api.sessions as sessions
from app.llm import active_embedding_model


def _stub_settings(provider):
    return types.SimpleNamespace(
        embedding_provider=provider,
        openai_embedding_model="text-embedding-3-small",
        gemini_embedding_model="gemini-embedding-001",
    )


def test_active_model_follows_provider(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: _stub_settings("openai"))
    assert active_embedding_model() == "text-embedding-3-small"
    monkeypatch.setattr("app.config.get_settings", lambda: _stub_settings("gemini"))
    assert active_embedding_model() == "gemini-embedding-001"


def test_guard_allows_matching_session(monkeypatch):
    monkeypatch.setattr(sessions, "active_embedding_model", lambda: "gemini-embedding-001")
    sessions._assert_embedding_current({"embedding_model": "gemini-embedding-001"})  # no raise


def test_guard_blocks_mismatched_session(monkeypatch):
    monkeypatch.setattr(sessions, "active_embedding_model", lambda: "gemini-embedding-001")
    with pytest.raises(HTTPException) as exc:
        sessions._assert_embedding_current({"embedding_model": "text-embedding-3-small"})
    assert exc.value.status_code == 409


def test_guard_treats_null_tag_as_openai(monkeypatch):
    # Dormant period: active is OpenAI; an untagged/null session must still pass.
    monkeypatch.setattr(sessions, "active_embedding_model", lambda: "text-embedding-3-small")
    sessions._assert_embedding_current({})  # no raise
    sessions._assert_embedding_current({"embedding_model": None})  # no raise
