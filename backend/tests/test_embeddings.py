"""Unit tests for the provider-pluggable embedding backends.

Covers the 2026-06-15 locked-decision override (OpenAI -> Gemini): the OpenAI
backend is unchanged behaviour, the Gemini backend builds the right REST request,
normalizes truncated vectors, chunks large batches, and validates the response;
and OpenAILLM still raises LLMError for callers.
"""

import math
import types

import pytest

from app.llm.embeddings import (
    EmbeddingError,
    GeminiEmbedder,
    OpenAIEmbedder,
    l2_normalize,
)
from app.llm.openai_client import LLMError, OpenAILLM


def _norm(vec):
    return math.sqrt(sum(x * x for x in vec))


def test_l2_normalize_unit_and_zero():
    assert _norm(l2_normalize([3.0, 4.0])) == pytest.approx(1.0)
    assert l2_normalize([0.0, 0.0]) == [0.0, 0.0]  # no div-by-zero


# ---------------------------------------------------------------- OpenAIEmbedder


class _FakeOpenAIClient:
    def __init__(self, embs):
        self._embs = embs
        self.calls = []
        self.embeddings = types.SimpleNamespace(create=self._create)

    def _create(self, model, input):  # noqa: A002 — mirrors the SDK kwarg name
        self.calls.append((model, list(input)))
        data = [types.SimpleNamespace(embedding=e) for e in self._embs[: len(input)]]
        return types.SimpleNamespace(data=data, usage=types.SimpleNamespace(total_tokens=7))


def test_openai_embedder_returns_vectors():
    client = _FakeOpenAIClient([[0.1, 0.2], [0.3, 0.4]])
    emb = OpenAIEmbedder(client, "text-embedding-3-small")
    assert emb.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]
    assert client.calls == [("text-embedding-3-small", ["a", "b"])]
    assert emb.model == "text-embedding-3-small"


def test_openai_embedder_empty_skips_call():
    client = _FakeOpenAIClient([])
    assert OpenAIEmbedder(client, "text-embedding-3-small").embed([]) == []
    assert client.calls == []


# ---------------------------------------------------------------- GeminiEmbedder


class _FakeHTTPResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _patch_post(monkeypatch, capture, values=(3.0, 4.0)):
    def fake_post(url, headers, json, timeout):
        capture.append({"url": url, "headers": headers, "json": json})
        n = len(json["requests"])
        return _FakeHTTPResp({"embeddings": [{"values": list(values)} for _ in range(n)]})

    monkeypatch.setattr("app.llm.embeddings.httpx.post", fake_post)


def test_gemini_requires_key():
    with pytest.raises(EmbeddingError):
        GeminiEmbedder(api_key="")


def test_gemini_builds_request_and_normalizes(monkeypatch):
    cap = []
    _patch_post(monkeypatch, cap)
    out = GeminiEmbedder(api_key="k", output_dim=2).embed(["x", "y"])
    assert len(out) == 2
    assert all(_norm(v) == pytest.approx(1.0) for v in out)  # truncated -> normalized
    req = cap[0]["json"]["requests"][0]
    assert req["model"] == "models/gemini-embedding-001"
    assert req["outputDimensionality"] == 2
    assert req["taskType"] == "SEMANTIC_SIMILARITY"
    assert req["content"]["parts"][0]["text"] == "x"
    assert cap[0]["headers"] == {"x-goog-api-key": "k"}  # key in header, not URL
    assert cap[0]["url"].endswith("/models/gemini-embedding-001:batchEmbedContents")


def test_gemini_chunks_batches_over_limit(monkeypatch):
    cap = []
    _patch_post(monkeypatch, cap)
    out = GeminiEmbedder(api_key="k", output_dim=2).embed([f"t{i}" for i in range(250)])
    assert len(out) == 250
    assert len(cap) == 3  # 100 + 100 + 50


def test_gemini_count_mismatch_raises(monkeypatch):
    monkeypatch.setattr(
        "app.llm.embeddings.httpx.post",
        lambda url, headers, json, timeout: _FakeHTTPResp({"embeddings": [{"values": [1.0]}]}),
    )
    with pytest.raises(EmbeddingError):
        GeminiEmbedder(api_key="k").embed(["a", "b"])


def test_gemini_empty_skips_call(monkeypatch):
    monkeypatch.setattr(
        "app.llm.embeddings.httpx.post",
        lambda *a, **k: pytest.fail("should not call the API for empty input"),
    )
    assert GeminiEmbedder(api_key="k").embed([]) == []


# ---------------------------------------------------- OpenAILLM delegates + wraps


class _BoomEmbedder:
    def embed(self, texts):
        raise EmbeddingError("boom")


def test_openaillm_wraps_embedding_error_as_llmerror():
    llm = OpenAILLM(
        api_key="x", silo_model="m", embedding_model="e", embedder=_BoomEmbedder()
    )
    with pytest.raises(LLMError):
        llm.embed(["a"])
