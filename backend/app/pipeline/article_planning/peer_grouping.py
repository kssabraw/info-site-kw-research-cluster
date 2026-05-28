"""Peer-entity-aware article grouping (owner-requested follow-up to §7.10).

Background: the orchestrator clusters by keyword embedding similarity. Keywords
that name DIFFERENT peer entities (e.g. `switching from tirzepatide to retatrutide`
vs. `switching from zepbound to retatrutide`) embed nearly identically — only the
peer-name token differs, and the model sees those tokens as semantically close —
so Louvain bundles them as one community and the orchestrator inherits one
combined article. But editorially they are DIFFERENT articles: each names a
different peer and must contain peer-specific guidance.

This pass uses the deterministic peer-entity list (already produced by grounding
at session creation, used by the §7.6 off-niche filter) to partition each
topic's planned articles by the peer entity each keyword names — and aggregates
across the topic's articles, so all `tirzepatide`-naming keywords in the topic
end up in ONE tirzepatide article regardless of which planner-article they
landed in. Multi-peer keywords (e.g. `retatrutide vs tirzepatide vs semaglutide`)
form their own multi-peer bucket.

Design choices:
- **No minimum size.** A peer mention is a deterministic signal — even one
  keyword naming a unique peer becomes its own primary (zero supporting kw is OK).
- **Whole-word peer match** (so brand-name substrings inside other tokens are
  safe), case-insensitive.
- **Runs BEFORE the salience split**, because peer-entity is a stronger semantic
  signal than embedding similarity; split then handles any oversized leftovers.
- **Per-topic** (not cross-silo). Cross-topic dedup runs after and merges any
  peer articles that appear in multiple silos (e.g. a tirzepatide article in
  both Mechanism and Obesity dedups to one).
"""

import logging
import re

from .models import ArticleRecord, PlanResult

logger = logging.getLogger(__name__)


def _peer_regex(peer_terms: list[str]) -> re.Pattern | None:
    cleaned = [p.strip().lower() for p in (peer_terms or []) if p and p.strip()]
    if not cleaned:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(p) for p in cleaned) + r")\b")


def _detect_peers(keyword: str, peer_lower: list[str]) -> frozenset[str]:
    """Return the set of peer entities the keyword names (whole-word, lowercase)."""
    kw_lower = keyword.lower()
    return frozenset(
        p for p in peer_lower if re.search(r"\b" + re.escape(p) + r"\b", kw_lower)
    )


def _pick_peer_primary(
    keywords: list[str], seed_lower: list[str], peer: str
) -> str:
    """Prefer the cleanest `seed vs peer` / `peer vs seed` form; else shortest."""
    versus_candidates: list[str] = []
    for kw in keywords:
        kw_lower = kw.lower()
        for seed in seed_lower:
            if re.search(rf"\b{re.escape(seed)}\s+vs\.?\s+{re.escape(peer)}\b", kw_lower) \
               or re.search(rf"\b{re.escape(peer)}\s+vs\.?\s+{re.escape(seed)}\b", kw_lower):
                versus_candidates.append(kw)
                break
    pool = versus_candidates or keywords
    return min(pool, key=lambda k: (len(k), k))


def _unique_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def group_by_peer_entity(
    result: PlanResult,
    *,
    seed_terms: list[str],
    peer_terms: list[str],
) -> None:
    """Mutate `result` in place: partition each topic's articles by peer entity.

    For each topic, every keyword that names ≥1 peer is pulled into a per-peer
    bucket (single-peer keywords) or a multi-peer bucket (frozenset). Buckets
    aggregate across the topic's planner-articles, so all keywords naming the
    same peer collapse into one article (the owner intent: one article per
    peer relationship with the seed). A planner-article keeps its non-peer
    keywords; if its primary was peer-named, a non-peer keyword is promoted.
    Articles whose every keyword was peer-named are consumed (dissolved into
    peer buckets)."""
    if not peer_terms:
        return
    regex = _peer_regex(peer_terms)
    if regex is None:
        return
    peer_lower = [p.strip().lower() for p in peer_terms if p and p.strip()]
    seed_lower = [s.strip().lower() for s in (seed_terms or []) if s and s.strip()]

    total_added = 0
    for plan in result.per_topic:
        # peer_key -> list of keywords (across all planner-articles in the topic)
        peer_buckets: dict[frozenset, list[str]] = {}
        rebuilt: list[ArticleRecord] = []

        for art in plan.articles:
            all_kws = _unique_preserving_order(
                [art.primary_keyword, *art.supporting_keywords]
            )
            non_peer: list[str] = []
            for kw in all_kws:
                peers = _detect_peers(kw, peer_lower)
                if peers:
                    peer_buckets.setdefault(peers, []).append(kw)
                else:
                    non_peer.append(kw)

            # Decide what survives of the original article.
            if not non_peer:
                continue  # every keyword was peer-named — parent dissolves
            if art.primary_keyword in non_peer:
                primary = art.primary_keyword
                notes = art.orchestrator_notes
            else:
                # Primary was peer-named (went to a peer bucket); promote a
                # non-peer keyword to be the parent's new primary.
                primary = min(non_peer, key=lambda k: (len(k), k))
                notes = (
                    (art.orchestrator_notes or "")
                    + " | primary promoted after peer-entity grouping"
                ).strip(" |")
            rebuilt.append(ArticleRecord(
                topic_id=art.topic_id,
                primary_keyword=primary,
                supporting_keywords=[k for k in non_peer if k != primary],
                intent=art.intent,
                suggested_h2s=art.suggested_h2s if primary == art.primary_keyword else [],
                source_statistical_grouping_id=art.source_statistical_grouping_id,
                orchestrator_notes=notes,
                serp_top_urls=art.serp_top_urls if primary == art.primary_keyword else [],
                peer_primary_keywords=art.peer_primary_keywords,
            ))

        # Materialize one article per peer bucket (deterministic — no minimum).
        for peer_key, kws in peer_buckets.items():
            unique = _unique_preserving_order(kws)
            if len(peer_key) == 1:
                (peer,) = peer_key
                primary = _pick_peer_primary(unique, seed_lower, peer)
                label = peer
            else:
                primary = min(unique, key=lambda k: (len(k), k))
                label = ", ".join(sorted(peer_key))
            rebuilt.append(ArticleRecord(
                topic_id=plan.topic_id,
                primary_keyword=primary,
                supporting_keywords=[k for k in unique if k != primary],
                intent="comparison",
                suggested_h2s=[],
                source_statistical_grouping_id=None,
                orchestrator_notes=f"Grouped by peer entity: {label}",
            ))

        delta = len(rebuilt) - len(plan.articles)
        plan.articles = rebuilt
        if delta:
            plan.log["peer_entity_grouped_delta"] = delta
            total_added += max(delta, 0)

    if total_added:
        logger.info(
            "step_complete",
            extra={"event": "step_complete", "step": "peer_entity_grouping",
                   "articles_added": total_added},
        )
