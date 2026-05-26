"""Anthropic wrapper for the article planning orchestrator (PRD §7.10, §14.2).

Claude Opus 4.7 in tool-use mode: the orchestrator is forced to emit its output
through a single tool whose `input_schema` is the §7.10.3 article-plan schema, so
the shape is enforced by the model rather than parsed out of prose. No browsing —
all evidence (SERPs, groupings, keyword pool) is in the prompt.

Every model call emits an `llm_call` structured log (PRD §16.3).
"""

import logging
import time

from anthropic import Anthropic

from app.cost_meter import llm_token_cost, record_cost

logger = logging.getLogger(__name__)


class AnthropicError(Exception):
    pass


class AnthropicLLM:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        max_tokens: int = 8000,
        timeout_s: float = 120.0,
    ):
        self._client = Anthropic(api_key=api_key, timeout=timeout_s)
        self._model = model
        self._max_tokens = max_tokens

    def call_tool(
        self,
        *,
        system: str,
        user: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
        purpose: str,
    ) -> dict:
        """Force a single tool call and return its `input` dict (the structured
        output). Raises AnthropicError on transport failure or a missing tool
        block; the caller owns reprompt/degrade policy (PRD §16.2)."""
        started = time.perf_counter()
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                tools=[
                    {
                        "name": tool_name,
                        "description": tool_description,
                        "input_schema": input_schema,
                    }
                ],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # noqa: BLE001 — surfaced as AnthropicError
            raise AnthropicError(f"Anthropic call failed ({purpose}): {exc}") from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        usage = getattr(resp, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        cost = llm_token_cost(self._model, input_tokens, output_tokens)
        record_cost(cost)  # PRD §16.4 — token-derived cost
        logger.info(
            "llm_call",
            extra={
                "event": "llm_call",
                "purpose": purpose,
                "provider": "anthropic",
                "model": self._model,
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "latency_ms": latency_ms,
                "cost_usd": cost,
                "status": "success",
            },
        )

        for block in resp.content or []:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                data = block.input
                if isinstance(data, dict):
                    return data
                raise AnthropicError(f"Tool input was not an object ({purpose})")
        raise AnthropicError(f"Model returned no tool_use block ({purpose})")
