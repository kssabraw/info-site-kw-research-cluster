"""OpenAI wrapper for silo discovery (PRD §7.1, Appendix B.1).

- Grounding pass: GPT-5.4 with web search reads top content for the bare seed,
  reports subject category + dominant audience, and judges ambiguity.
- Silo proposal: GPT-5.4 with web search proposes silos as strict JSON.
- Embeddings: text-embedding-3-small for the per-silo relevance anchor.

Every model call emits an `llm_call` structured log (PRD §16.3).
"""

import json
import logging
import re
import time

from openai import OpenAI

from app.pipeline.models import (
    PROPOSABLE_TYPES,
    GroundingResult,
    ProposedSilo,
    RelationshipType,
)

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


def _extract_json(text: str):
    """Parse JSON from a model response, tolerating prose or code fences."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the first {...} or [...] span.
        for opener, closer in (("{", "}"), ("[", "]")):
            start, end = text.find(opener), text.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
    raise LLMError("Model did not return valid JSON")


class OpenAILLM:
    def __init__(
        self,
        api_key: str,
        silo_model: str,
        embedding_model: str,
        web_search_tool: str = "web_search",
    ):
        self._client = OpenAI(api_key=api_key)
        self._silo_model = silo_model
        self._embedding_model = embedding_model
        self._web_search_tool = web_search_tool

    def _respond(self, prompt: str, purpose: str, *, browsing: bool) -> str:
        started = time.perf_counter()
        kwargs: dict = {"model": self._silo_model, "input": prompt}
        if browsing:
            kwargs["tools"] = [{"type": self._web_search_tool}]
        try:
            resp = self._client.responses.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 — surfaced as LLMError to caller
            raise LLMError(f"OpenAI call failed ({purpose}): {exc}") from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        usage = getattr(resp, "usage", None)
        logger.info(
            "llm_call",
            extra={
                "event": "llm_call",
                "purpose": purpose,
                "provider": "openai",
                "model": self._silo_model,
                "prompt_tokens": getattr(usage, "input_tokens", None),
                "completion_tokens": getattr(usage, "output_tokens", None),
                "latency_ms": latency_ms,
                "status": "success",
            },
        )
        text = getattr(resp, "output_text", None)
        if not text:
            raise LLMError(f"Empty model response ({purpose})")
        return text

    def ground_subject(self, seed: str, disambiguation_hint: str | None) -> GroundingResult:
        hint_line = (
            f"The user clarified the intended meaning: {disambiguation_hint}\n"
            if disambiguation_hint
            else ""
        )
        prompt = (
            f"Research the topic '{seed}' using web search and summarize what it is.\n"
            f"{hint_line}"
            "Return ONLY a JSON object with keys:\n"
            '  "summary": ~400 word plain-text overview of the subject,\n'
            '  "subject_category": short category label (e.g. drug, product, concept, location),\n'
            '  "detected_audience": the dominant audience for top-ranking content,\n'
            '  "is_ambiguous": true if the seed clearly refers to two or more disjoint subjects '
            "(e.g. a planet AND a chemical element), otherwise false,\n"
            '  "interpretations": when ambiguous, a list of short distinct interpretation labels; else [].\n'
        )
        data = _extract_json(self._respond(prompt, "subject_grounding", browsing=True))
        # A supplied disambiguation hint resolves ambiguity outright (PRD §7.1.2).
        is_ambiguous = bool(data.get("is_ambiguous")) and not disambiguation_hint
        return GroundingResult(
            summary=str(data.get("summary", "")),
            subject_category=data.get("subject_category"),
            detected_audience=data.get("detected_audience"),
            is_ambiguous=is_ambiguous,
            interpretations=[str(i) for i in (data.get("interpretations") or [])],
        )

    def propose_silos(
        self,
        seed: str,
        topic_count: int,
        audience: str | None,
        grounding_summary: str,
        demand_keywords: list[str],
        competitor_paths: list[str],
    ) -> list[ProposedSilo]:
        prompt = self._silo_prompt(
            seed, topic_count, audience, grounding_summary, demand_keywords, competitor_paths
        )
        # One reprompt if the first attempt yields no valid on-taxonomy silos
        # (PRD §5.2: off-taxonomy returns are reprompted, max two attempts).
        last_error: str | None = None
        for attempt in range(2):
            text = self._respond(
                prompt
                if last_error is None
                else f"{prompt}\n\nYour previous response was rejected: {last_error}\n"
                "Return a corrected strict JSON array.",
                "silo_proposal",
                browsing=True,
            )
            try:
                raw = _extract_json(text)
            except LLMError as exc:
                last_error = str(exc)
                continue
            silos = self._parse_silos(raw)
            if silos:
                return silos
            last_error = "No valid, on-taxonomy silos were returned."
        return []

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        started = time.perf_counter()
        try:
            resp = self._client.embeddings.create(model=self._embedding_model, input=texts)
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Embedding call failed: {exc}") from exc
        logger.info(
            "external_call",
            extra={
                "event": "external_call",
                "service": "openai",
                "endpoint": "embeddings",
                "result_count": len(texts),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return [d.embedding for d in resp.data]

    @staticmethod
    def _parse_silos(raw) -> list[ProposedSilo]:
        if isinstance(raw, dict):
            raw = raw.get("silos") or raw.get("topics") or []
        if not isinstance(raw, list):
            return []
        silos: list[ProposedSilo] = []
        for item in raw:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            try:
                rel = RelationshipType(item.get("relationship_type"))
            except ValueError:
                continue  # off-taxonomy — drop (PRD §5.2)
            if rel not in PROPOSABLE_TYPES:
                continue  # peer_entity filtered before display (PRD §5.1)
            silos.append(
                ProposedSilo(
                    name=str(item["name"]).strip(),
                    rationale=str(item.get("rationale", "")).strip(),
                    relationship_type=rel,
                    supporting_evidence=(
                        str(item["supporting_evidence"]).strip()
                        if item.get("supporting_evidence")
                        else None
                    ),
                    is_broader_class=bool(item.get("is_broader_class"))
                    or rel is RelationshipType.broader_class,
                )
            )
        return silos

    @staticmethod
    def _silo_prompt(
        seed: str,
        topic_count: int,
        audience: str | None,
        grounding_summary: str,
        demand_keywords: list[str],
        competitor_paths: list[str],
    ) -> str:
        demand = "\n".join(f"- {k}" for k in demand_keywords[:30]) or "- (none available)"
        paths = "\n".join(f"- {p}" for p in competitor_paths) or "- (none available)"
        audience_line = audience or "(infer from the grounding summary)"
        return f"""You are proposing the top-level subfolder structure for a niche authority site about {seed}.

The site will be dedicated entirely to {seed}. Every article on it must serve someone researching, evaluating, or using {seed}.

AUDIENCE: {audience_line}

EVIDENCE GATHERED:
Subject grounding summary:
{grounding_summary}

Top keywords from the demand sample:
{demand}

Top competitor URL path patterns:
{paths}

YOUR JOB:
Propose {topic_count} subfolders ("silos") that together cover what this site needs to demonstrate topical authority. Each silo becomes a top-level section of the site with multiple articles inside it.

RULES:
1. Every silo must be tagged with one of these relationship_types:
   - property_or_mechanism: something {seed} IS or DOES
   - use_case: an application or scenario where {seed} is used
   - effect_or_outcome: what happens as a result of {seed}
   - practical_commercial: how someone obtains, uses, or operationalizes {seed}
   - research_or_trial: scientific evidence about {seed}
   - broader_class: a category that contains {seed} (use SPARINGLY; justify why a {seed} site needs this category-level coverage)
2. NEVER propose a peer entity as a silo. Peer entities are other things in the same category as {seed} (e.g. competing drugs, competing products, sibling concepts). They dilute topical authority.
3. Every silo must cite specific evidence in `supporting_evidence` — a keyword cluster from the demand sample, a competitor URL pattern, or an explicit reference to a fact from the grounding.

OUTPUT FORMAT:
Return ONLY a strict JSON array of {topic_count} objects:
[
  {{
    "name": "short name, 2-5 words",
    "rationale": "2-3 sentences on why this silo is essential for topical authority",
    "relationship_type": "one of the enums above",
    "supporting_evidence": "specific evidence from the materials provided",
    "is_broader_class": false
  }}
]"""
