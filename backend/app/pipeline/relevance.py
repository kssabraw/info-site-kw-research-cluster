"""Relevance gate + dedup + junk filter (PRD §7.6).

Every candidate keyword is checked against its parent topic's embedding by
cosine similarity. This is the pipeline's volume control point — and the step
that finally sorts the seed-level keyword pool (suggestions/fan-outs were fanned
to every silo in §7.3) into the silo each keyword actually belongs to.

- Cross-source dedup happens upstream: the per-topic pools are keyed by the
  normalized keyword, so duplicate surfacings already merged while preserving
  source attribution. Here we only score and classify.
- Junk filter (cheap, pre-embedding): blocked tokens + length sanity.
- Relevance: cosine >= threshold (default 0.62) -> active, else
  filtered_relevance. Junk -> filtered_junk. Nothing is deleted; failures are
  tagged and stored for v1 calibration.

Embeddings computed here for surviving keywords are returned so the clustering
step (§7.9) can reuse them rather than re-embedding.
"""

import logging
import re
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# Blocked tokens (PRD §7.6). Conservative whole-word blocklist; a keyword is junk
# if any of its words is blocked. Brand-name detection (the third §7.6 sub-rule)
# needs a brand DB and is left out of v1 — flagged for later calibration.
_BLOCKED_TOKENS = frozenset({
    "porn", "porno", "pornography", "xxx", "nsfw", "sex", "escort", "escorts",
    "casino", "casinos", "gambling", "betting", "bet", "poker", "slots",
    "viagra", "cialis",
})
_MIN_CHARS = 2
_MAX_WORDS = 12

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass
class GatedKeyword:
    keyword: str
    sources: list[str]
    status: str  # 'active' | 'filtered_relevance' | 'filtered_junk'
    relevance_score: float | None = None
    embedding: list[float] | None = None  # kept only for 'active' (for §7.9)


@dataclass
class RelevanceResult:
    # topic_id -> list of classified keywords
    per_topic: dict[str, list[GatedKeyword]] = field(default_factory=dict)
    degraded_notes: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = {"active": 0, "filtered_relevance": 0, "filtered_junk": 0}
        for kws in self.per_topic.values():
            for k in kws:
                out[k.status] = out.get(k.status, 0) + 1
        return out


def _is_junk(keyword: str) -> bool:
    if len(keyword) < _MIN_CHARS:
        return True
    words = _WORD_RE.findall(keyword)
    if not words or len(words) > _MAX_WORDS:
        return True
    return any(w in _BLOCKED_TOKENS for w in words)


def _cosine_to_anchor(vectors: np.ndarray, anchor: np.ndarray) -> np.ndarray:
    """Cosine similarity of each row in `vectors` to `anchor`. Zero vectors yield 0."""
    anchor_norm = np.linalg.norm(anchor)
    if anchor_norm == 0:
        return np.zeros(vectors.shape[0])
    row_norms = np.linalg.norm(vectors, axis=1)
    safe = np.where(row_norms == 0, 1.0, row_norms)
    sims = (vectors @ anchor) / (safe * anchor_norm)
    return np.where(row_norms == 0, 0.0, sims)


def run_relevance_gate(
    *,
    per_topic: dict[str, dict[str, list[str]]],
    topic_embeddings: dict[str, list[float] | None],
    embed_fn,
    topic_names: dict[str, str] | None = None,
    threshold: float = 0.62,
    batch_size: int = 1000,
) -> RelevanceResult:
    """Classify every keyword in `per_topic` as active / filtered_relevance /
    filtered_junk. `embed_fn(list[str]) -> list[list[float]]` embeds keywords.
    A topic with no embedding can't be scored — its keywords are kept active
    (score null) and the run is flagged degraded for that silo."""
    result = RelevanceResult()
    topic_names = topic_names or {}

    for tid, pool in per_topic.items():
        classified: list[GatedKeyword] = []
        candidates: list[str] = []  # non-junk, to embed
        candidate_sources: list[list[str]] = []

        for kw, sources in pool.items():
            if _is_junk(kw):
                classified.append(GatedKeyword(kw, sorted(sources), "filtered_junk"))
            else:
                candidates.append(kw)
                candidate_sources.append(sorted(sources))

        anchor = topic_embeddings.get(tid)
        if not candidates:
            result.per_topic[tid] = classified
            continue

        if not anchor:
            # No topic embedding -> can't gate. Keep active, score null, degrade.
            label = topic_names.get(tid) or tid
            result.degraded_notes.append(
                f"Relevance gate skipped for silo “{label}”: no topic embedding."
            )
            for kw, sources in zip(candidates, candidate_sources):
                classified.append(GatedKeyword(kw, sources, "active"))
            result.per_topic[tid] = classified
            continue

        anchor_vec = np.asarray(anchor, dtype=np.float64)
        # Embed candidates in batches to bound request size.
        embeddings: list[list[float]] = []
        for start in range(0, len(candidates), batch_size):
            embeddings.extend(embed_fn(candidates[start : start + batch_size]))

        vectors = np.asarray(embeddings, dtype=np.float64)
        sims = _cosine_to_anchor(vectors, anchor_vec)
        for kw, sources, emb, sim in zip(candidates, candidate_sources, embeddings, sims):
            score = float(sim)
            if score >= threshold:
                classified.append(
                    GatedKeyword(kw, sources, "active", relevance_score=score, embedding=emb)
                )
            else:
                classified.append(
                    GatedKeyword(kw, sources, "filtered_relevance", relevance_score=score)
                )
        result.per_topic[tid] = classified

    counts = result.counts()
    logger.info(
        "step_complete",
        extra={"event": "step_complete", "step": "relevance_gate",
               "active": counts["active"],
               "filtered_relevance": counts["filtered_relevance"],
               "filtered_junk": counts["filtered_junk"],
               "threshold": threshold},
    )
    return result
