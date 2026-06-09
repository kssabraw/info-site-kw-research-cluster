"""Site architecture generation (PRD §7.11, prompt B.3).

The final pipeline step. Each accepted silo (that produced at least one article)
becomes a pillar: a higher-level overview page that links down to its supporting
articles. Opus 4.7 writes the pillar's *editorial* fields (title, target keyword,
summary, H2 outline) — the "structured editorial reasoning" §7.11 wants the LLM
for — while the *linking matrix* is assembled deterministically so the §15.2
acceptance rules hold by construction rather than by trusting the model:

  1. one pillar per accepted (article-bearing) silo;
  2. every supporting article links up to its pillar (mandatory);
  3. no orphans — every supporting article is reachable from its pillar's
     down-links, so the graph has no orphan node;
  4. pillars link laterally only where topic-embedding cosine > the threshold.

This mirrors M5's cross-topic dedup, which was likewise made deterministic
(reproducible + testable) rather than a single LLM call. Divergence from B.3
(which has the model emit the link structure too) is intentional and flagged.

A per-pillar LLM failure degrades that pillar to a deterministic stub (title =
silo name, outline from its article names) without sinking the run; if *every*
pillar degrades the caller treats it as an error (the architecture would just be
silo names relabeled).
"""

import logging
import random
import time
from concurrent.futures import as_completed

import numpy as np

from app.concurrency import ContextThreadPoolExecutor as ThreadPoolExecutor
from app.llm import AnthropicError, AnthropicLLM

from .models import (
    ArchitectureResult,
    ArticleInput,
    Pillar,
    PillarInput,
    SupportingArticle,
)

logger = logging.getLogger(__name__)

_TOOL_NAME = "submit_pillar"
_TOOL_DESCRIPTION = (
    "Emit the pillar overview for this silo: a working title, the broadest "
    "commercially-meaningful target keyword, and a short summary. The H2 outline "
    "is NOT produced here — the writer module generates it at write time."
)

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "target_keyword": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["title", "target_keyword", "summary"],
}

_SYSTEM = """You are designing the site architecture for a niche authority site. For one silo, you write the PILLAR PAGE: a high-level overview article that establishes the silo's authority and links down to all its supporting articles.

You are given the silo and the list of supporting articles already planned for it (you do NOT re-plan or invent articles).

Produce, via the submit_pillar tool:
- title: a real, compelling article title that reflects the silo (e.g. "The Complete Guide to Triple Agonist Drugs"), not just the silo's raw name.
- target_keyword: the broadest commercially-meaningful keyword for the silo as a whole (the pillar competes for the head term, the supporting articles for the long tail).
- summary: 1-2 sentences describing what the pillar covers.

Do NOT produce an H2 outline — the writer module generates the pillar's headings at write time.

Emit your answer through the submit_pillar tool only."""


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _build_pillar_prompt(pillar: PillarInput, seed: str, audience: str) -> str:
    article_lines = "\n".join(
        f"    - {a.name} (primary keyword: {a.primary_keyword}; intent: {a.intent})"
        for a in pillar.articles
    )
    return (
        f"SITE SEED: {seed}\n"
        f"AUDIENCE: {audience or '(unspecified)'}\n\n"
        f"SILO: {pillar.silo_name}\n"
        f"Relationship to the seed: {pillar.relationship_type}\n"
        f"Rationale: {pillar.rationale or '(none)'}\n\n"
        f"SUPPORTING ARTICLES ({len(pillar.articles)}):\n{article_lines}\n\n"
        "Write the pillar overview for this silo via the submit_pillar tool."
    )


def _stub_pillar_content(pillar: PillarInput, *, reason: str) -> dict:
    """Degraded fallback (PRD §16.2): a usable-but-plain pillar derived from the
    silo + its article names, no LLM. The H2 outline is left empty — the writer
    module generates pillar headings at write time."""
    logger.warning(
        "degraded",
        extra={"event": "degraded", "step": "architecture", "topic_id": pillar.topic_id,
               "reason": reason},
    )
    return {
        "title": pillar.silo_name,
        "target_keyword": pillar.silo_name.lower(),
        "summary": f"Overview of {pillar.silo_name}.",
        "h2_outline": [],
        "degraded": True,
    }


_MAX_ATTEMPTS = 3


def _write_pillar_content(
    pillar: PillarInput, architect: AnthropicLLM, *, seed: str, audience: str
) -> dict:
    """Get the LLM's editorial fields for one pillar. Retries on a transport/shape
    failure, then degrades to a deterministic stub for this pillar only (PRD
    §16.2). On a transport error (rate-limit / overload — the dominant failure when
    several pillars fire at once) it backs off before retrying, since the SDK's own
    retries and an immediate reprompt all land in the same throttling window; a
    shape failure reprompts immediately (no point waiting)."""
    user = _build_pillar_prompt(pillar, seed, audience)
    last_error: str | None = None
    for attempt in range(_MAX_ATTEMPTS):
        prompt = user if last_error is None else (
            f"{user}\n\nYour previous response could not be used: {last_error}\n"
            "Return a corrected pillar via the submit_pillar tool."
        )
        try:
            raw = architect.call_tool(
                system=_SYSTEM,
                user=prompt,
                tool_name=_TOOL_NAME,
                tool_description=_TOOL_DESCRIPTION,
                input_schema=_INPUT_SCHEMA,
                purpose="site_architecture",
            )
        except AnthropicError as exc:
            last_error = str(exc)
            if attempt < _MAX_ATTEMPTS - 1:
                # Exponential backoff with jitter to spread retries out of the
                # shared rate-limit window (1.5s, 3s, capped) before reprompting.
                time.sleep(min(8.0, 1.5 * (2 ** attempt)) + random.uniform(0, 0.5))
            continue
        title = str(raw.get("title") or "").strip()
        target = str(raw.get("target_keyword") or "").strip()
        if not title or not target:
            last_error = "title and target_keyword are required"
            continue
        # H2 outline is owned by the writer module, not the architect — persist an
        # empty list (kept on the model so the writer can fill it later).
        return {
            "title": title,
            "target_keyword": target,
            "summary": str(raw.get("summary") or "").strip(),
            "h2_outline": [],
            "degraded": False,
        }
    return _stub_pillar_content(pillar, reason=last_error or "architect failed")


def _lateral_pillar_links(
    pillar_topic_ids: list[str],
    topic_embeddings: dict[str, list[float] | None],
    threshold: float,
    max_per_pillar: int,
) -> dict[str, list[str]]:
    """topic_id -> peer topic_ids whose topic-embedding cosine exceeds `threshold`
    (PRD §7.11 / §15.2 #4), with each pillar's outbound list capped at the top
    `max_per_pillar` peers by cosine. Silos without an embedding get no links.

    Note: the cap is applied per-pillar, so the resulting graph may be mildly
    asymmetric — A's list can include B while B's top-N omits A if B sits at
    the center of a denser neighborhood. That's the right call: each pillar
    points at its most-related peers, not at every peer above the bar."""
    vecs = {
        tid: np.asarray(topic_embeddings[tid], dtype=np.float32)
        for tid in pillar_topic_ids
        if topic_embeddings.get(tid) is not None
    }
    # First pass: collect (cosine, peer) for every above-threshold pair.
    scored: dict[str, list[tuple[float, str]]] = {tid: [] for tid in pillar_topic_ids}
    ids = list(vecs.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            cos = _cosine(vecs[ids[i]], vecs[ids[j]])
            if cos > threshold:
                scored[ids[i]].append((cos, ids[j]))
                scored[ids[j]].append((cos, ids[i]))
    # Per pillar, keep its top-N peers by cosine (descending). max_per_pillar
    # <= 0 disables the cap (returns every above-threshold peer).
    links: dict[str, list[str]] = {}
    for tid, peers in scored.items():
        peers.sort(reverse=True)
        if max_per_pillar and max_per_pillar > 0:
            peers = peers[:max_per_pillar]
        links[tid] = [pid for _, pid in peers]
    return links


def _lateral_article_links(
    article: ArticleInput,
    same_silo_ids: set[str],
    cluster_centroids: dict[str, list[float] | None],
    *,
    max_links: int,
) -> list[str]:
    """2-3 lateral links to peer supporting articles (PRD §7.11), prioritizing the
    `peer_article_links` already set by the orchestrator / dedup, then topping up
    with the nearest same-silo peers by centroid cosine. Capped at `max_links`."""
    chosen: list[str] = []
    seen = {article.id}
    # Priority: existing peer links (may cross silos — from cross-topic dedup).
    for pid in article.peer_article_links:
        if pid not in seen and len(chosen) < max_links:
            chosen.append(pid)
            seen.add(pid)
    if len(chosen) >= max_links:
        return chosen
    # Top up with nearest same-silo peers by centroid similarity.
    own = cluster_centroids.get(article.id)
    if own is not None:
        own_vec = np.asarray(own, dtype=np.float32)
        scored: list[tuple[float, str]] = []
        for cid in same_silo_ids:
            if cid in seen:
                continue
            vec = cluster_centroids.get(cid)
            if vec is None:
                continue
            scored.append((_cosine(own_vec, np.asarray(vec, dtype=np.float32)), cid))
        scored.sort(reverse=True)
        for _, cid in scored:
            if len(chosen) >= max_links:
                break
            chosen.append(cid)
            seen.add(cid)
    return chosen


def run_architecture_generation(
    *,
    seed: str,
    audience: str,
    pillars_input: list[PillarInput],
    architect: AnthropicLLM,
    topic_embeddings: dict[str, list[float] | None],
    cluster_centroids: dict[str, list[float] | None],
    skipped_silos: list[str] | None = None,
    pillar_lateral_cosine_threshold: float = 0.55,
    pillar_lateral_links_max: int = 5,
    lateral_article_links_max: int = 3,
    max_workers: int = 5,
) -> ArchitectureResult:
    """Full §7.11 pass: write each pillar's editorial fields (LLM, parallel per
    silo), then assemble the linking matrix deterministically. Persistence is the
    caller's job."""
    result = ArchitectureResult(
        seed_keyword=seed, detected_audience=audience,
        skipped_silos=list(skipped_silos or []),
    )
    if not pillars_input:
        return result

    # ---- LLM editorial content per pillar (parallel) ---------------------
    content: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as ex:
        futures = {
            ex.submit(_write_pillar_content, p, architect, seed=seed, audience=audience): p.topic_id
            for p in pillars_input
        }
        for fut in as_completed(futures):
            content[futures[fut]] = fut.result()

    # ---- deterministic linking matrix ------------------------------------
    pillar_topic_ids = [p.topic_id for p in pillars_input]
    lateral_pillars = _lateral_pillar_links(
        pillar_topic_ids,
        topic_embeddings,
        pillar_lateral_cosine_threshold,
        pillar_lateral_links_max,
    )

    for p in pillars_input:
        c = content[p.topic_id]
        article_ids = [a.id for a in p.articles]
        result.pillars.append(
            Pillar(
                topic_id=p.topic_id,
                silo_name=p.silo_name,
                title=c["title"],
                target_keyword=c["target_keyword"],
                summary=c["summary"],
                h2_outline=c["h2_outline"],
                supporting_article_ids=article_ids,  # pillar links DOWN to all (#2/#3)
                lateral_pillar_links=lateral_pillars.get(p.topic_id, []),
                degraded=c["degraded"],
            )
        )
        same_silo_ids = set(article_ids)
        for a in p.articles:
            result.supporting_articles.append(
                SupportingArticle(
                    article_id=a.id,
                    name=a.name,
                    intent=a.intent,
                    parent_pillar_topic_id=p.topic_id,  # links UP to its pillar (#2)
                    lateral_article_links=_lateral_article_links(
                        a, same_silo_ids, cluster_centroids,
                        max_links=lateral_article_links_max,
                    ),
                )
            )

    logger.info(
        "step_complete",
        extra={"event": "step_complete", "step": "site_architecture", **result.counts()},
    )
    return result
