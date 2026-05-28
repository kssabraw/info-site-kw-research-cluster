"""Orchestrator Anthropic client: transient-transport backoff/retry.

The M5 orchestrator used to make a single `messages.create` — any exception
(incl. a 429 rate-limit under the parallel fan-out) degraded the whole chunk to
passthrough (e.g. a competitor article left as a raw Louvain grouping). The
client now retries transient transport errors with backoff before giving up,
mirroring the M6 architect. Shape failures still fail fast (the caller reprompts).
"""

import httpx
import pytest

import app.llm.anthropic_client as ac
from app.llm.anthropic_client import AnthropicError, AnthropicLLM


class _Usage:
    input_tokens = 10
    output_tokens = 20


class _ToolBlock:
    type = "tool_use"
    name = "plan"
    input = {"ok": True}


class _Resp:
    usage = _Usage()
    content = [_ToolBlock()]


class _Messages:
    """A fake `client.messages` whose `create` raises `exc` the first
    `fail_times` calls, then returns a well-formed tool response."""

    def __init__(self, fail_times: int, exc: Exception):
        self.calls = 0
        self._fail_times = fail_times
        self._exc = exc

    def create(self, **_kwargs):
        self.calls += 1
        if self.calls <= self._fail_times:
            raise self._exc
        return _Resp()


class _Client:
    def __init__(self, messages: _Messages):
        self.messages = messages


def _llm(messages: _Messages, *, max_attempts: int = 4) -> AnthropicLLM:
    llm = AnthropicLLM(api_key="test", model="claude-opus-4-7",
                       max_transport_attempts=max_attempts)
    llm._client = _Client(messages)
    return llm


def _call(llm: AnthropicLLM) -> dict:
    return llm.call_tool(
        system="s", user="u", tool_name="plan",
        tool_description="d", input_schema={"type": "object"}, purpose="test",
    )


def _conn_error() -> Exception:
    # APIConnectionError is in the retryable set and constructs without a response.
    return ac.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com")
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(ac.time, "sleep", lambda *_a, **_k: None)


def test_retries_transient_error_then_succeeds():
    msgs = _Messages(fail_times=2, exc=_conn_error())
    result = _call(_llm(msgs))
    assert result == {"ok": True}
    assert msgs.calls == 3  # two failures + one success


def test_raises_after_exhausting_transport_retries():
    msgs = _Messages(fail_times=99, exc=_conn_error())
    with pytest.raises(AnthropicError):
        _call(_llm(msgs, max_attempts=3))
    assert msgs.calls == 3  # tried exactly max_transport_attempts times


def test_does_not_retry_non_transport_error():
    """A non-transport exception (e.g. a bug, auth) fails fast — no backoff
    loop burning attempts on something that won't clear."""
    msgs = _Messages(fail_times=99, exc=ValueError("not a transport error"))
    with pytest.raises(AnthropicError):
        _call(_llm(msgs, max_attempts=4))
    assert msgs.calls == 1


def test_is_retryable_classifies_status_codes():
    req = httpx.Request("POST", "https://api.anthropic.com")
    resp_529 = httpx.Response(529, request=req)
    overloaded = ac.APIStatusError("overloaded", response=resp_529, body=None)
    assert ac._is_retryable(overloaded) is True

    resp_400 = httpx.Response(400, request=req)
    bad = ac.APIStatusError("bad request", response=resp_400, body=None)
    assert ac._is_retryable(bad) is False
