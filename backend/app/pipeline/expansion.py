"""Per-silo keyword expansion (PRD §7.3) + autocomplete enrichment (§7.5).

For each finalized silo, four DataForSEO endpoints run in parallel
(keyword_ideas, keyword_suggestions, query_fanouts, PAA two tiers deep). The
deduped keyword pool is then enriched via autocomplete. A failure on one
endpoint degrades that silo's pool but never blocks the others (§16.2).

M3 stops here: keywords are persisted raw with source attribution. Relevance
gating, competitor mining, and clustering are M4.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from app.dataforseo import DataForSEOClient, DataForSEOError

logger = logging.getLogger(__name__)


@dataclass
class ExpansionTopic:
    id: str
    anchor: str


@dataclass
class ExpansionResult:
    # topic_id -> {normalized_keyword: sorted list of source tags}
    per_topic: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    degraded_notes: list[str] = field(default_factory=list)

    @property
    def total_keywords(self) -> int:
        return sum(len(kws) for kws in self.per_topic.values())


def _normalize(kw: str) -> str:
    return " ".join(kw.strip().lower().split())


def _add(pool: dict[str, set[str]], keyword: str, source: str) -> None:
    norm = _normalize(keyword)
    if norm:
        pool.setdefault(norm, set()).add(source)


def run_expansion(
    *,
    topics: list[ExpansionTopic],
    dfs: DataForSEOClient,
    keyword_ideas_limit: int = 1000,
    keyword_suggestions_limit: int = 500,
    query_fanouts_limit: int = 300,
    paa_tier1_seeds: int = 8,
    paa_tier2_cap: int = 40,
    autocomplete_max: int = 1500,
    max_workers: int = 8,
) -> ExpansionResult:
    result = ExpansionResult()
    # topic_id -> {keyword: set(sources)}
    pools: dict[str, dict[str, set[str]]] = {t.id: {} for t in topics}

    def paa_two_tier(anchor: str) -> tuple[list[str], list[str]]:
        tier1 = dfs.people_also_ask(anchor)
        tier2: list[str] = []
        for q in tier1[:paa_tier1_seeds]:
            if len(tier2) >= paa_tier2_cap:
                break
            try:
                tier2.extend(dfs.people_also_ask(q))
            except DataForSEOError:
                continue
        return tier1, tier2[:paa_tier2_cap]

    # ----- Phase 1: base expansion (parallel across topic x endpoint) -------
    base_jobs = {
        "keyword_ideas": lambda a: dfs.keyword_ideas(a, keyword_ideas_limit),
        "keyword_suggestions": lambda a: dfs.keyword_suggestions(a, keyword_suggestions_limit),
        "query_fanouts": lambda a: dfs.query_fanouts(a, query_fanouts_limit),
        "paa": paa_two_tier,
    }

    with ThreadPoolExecutor(max_workers=max_workers) as pool_exec:
        futures = {}
        for t in topics:
            for source, fn in base_jobs.items():
                futures[pool_exec.submit(fn, t.anchor)] = (t, source)

        for fut in as_completed(futures):
            topic, source = futures[fut]
            try:
                data = fut.result()
            except DataForSEOError as exc:
                result.degraded_notes.append(
                    f"Partial expansion for silo “{topic.anchor}”: {source} unavailable."
                )
                logger.warning(
                    "degraded",
                    extra={"event": "degraded", "step": "expansion",
                           "topic": topic.anchor, "source": source, "reason": str(exc)},
                )
                continue
            if source == "paa":
                tier1, tier2 = data
                for kw in tier1:
                    _add(pools[topic.id], kw, "paa_t1")
                for kw in tier2:
                    _add(pools[topic.id], kw, "paa_t2")
            else:
                for kw in data:
                    _add(pools[topic.id], kw, source)

    # ----- Phase 2: autocomplete on the deduped pool (§7.5) -----------------
    # (topic_id, keyword) pairs, capped globally to bound cost.
    seeds: list[tuple[str, str]] = [
        (tid, kw) for tid, kws in pools.items() for kw in kws.keys()
    ][:autocomplete_max]

    if seeds:
        ok = 0
        fail = 0
        ac_additions: list[tuple[str, str]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool_exec:
            ac_futures = {pool_exec.submit(dfs.autocomplete, kw): tid for tid, kw in seeds}
            for fut in as_completed(ac_futures):
                tid = ac_futures[fut]
                try:
                    suggestions = fut.result()
                    ok += 1
                except DataForSEOError:
                    fail += 1
                    continue
                for sug in suggestions:
                    ac_additions.append((tid, sug))

        # Skip autocomplete entirely if a majority of calls failed (§16.2).
        if fail and fail / (ok + fail) > 0.5:
            result.degraded_notes.append("Autocomplete enrichment unavailable for this run.")
        else:
            for tid, sug in ac_additions:
                _add(pools[tid], sug, "autocomplete")

    result.per_topic = {
        tid: {kw: sorted(sources) for kw, sources in kws.items()}
        for tid, kws in pools.items()
    }
    logger.info(
        "step_complete",
        extra={"event": "step_complete", "step": "expansion",
               "topic_count": len(topics), "keyword_count": result.total_keywords,
               "degraded": bool(result.degraded_notes)},
    )
    return result
