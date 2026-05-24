"""Full M4 refinement pipeline (PRD §7.3–§7.9 composition).

Wires the per-stage modules into one run:

  1. §7.3/§7.5 expansion + autocomplete  -> per-topic candidate pool
  2. §7.4 competitor mining               -> gated silos' anchors + the seed
                                             (the seed is always mined; its
                                             keywords fan to every silo)
  3. §7.6 relevance gate + junk filter    -> active / filtered_* per topic
  4. §7.9 statistical clustering          -> per-topic Louvain groupings

Autocomplete (§7.5) is run inside expansion on the expansion pool only;
competitor keywords are already real ranked keywords and are not re-autocompleted
(a minor, documented deviation from §7.5's "after 7.3 and 7.4" ordering).

The run is synchronous and compounds the per-stage time budgets — a large run can
outrun the gateway. Background execution is deferred to M11 (handoff §4).
"""

import logging
from dataclasses import dataclass, field

from app.dataforseo import DataForSEOClient
from app.pipeline.clustering import run_clustering
from app.pipeline.competitor import MineTopic, run_competitor_mining
from app.pipeline.expansion import ExpansionTopic, build_anchor, run_expansion
from app.pipeline.relevance import GatedKeyword, run_relevance_gate

logger = logging.getLogger(__name__)

_SEED_MINE_ID = "__seed__"


@dataclass
class PipelineTopic:
    id: str
    name: str
    embedding: list[float] | None = None
    gated: bool = False


@dataclass
class PipelineResult:
    per_topic_gated: dict[str, list[GatedKeyword]] = field(default_factory=dict)
    clustering_log: dict = field(default_factory=dict)
    degraded_notes: list[str] = field(default_factory=list)
    timed_out: bool = False

    def counts(self) -> dict[str, int]:
        out = {"active": 0, "filtered_relevance": 0, "filtered_junk": 0}
        for kws in self.per_topic_gated.values():
            for k in kws:
                out[k.status] = out.get(k.status, 0) + 1
        return out


def _merge(base: dict[str, dict[str, set[str]]], add: dict[str, dict[str, list[str]]]) -> None:
    for tid, kws in add.items():
        target = base.get(tid)
        if target is None:
            continue
        for kw, sources in kws.items():
            target.setdefault(kw, set()).update(sources)


def run_refinement_pipeline(
    *,
    seed: str,
    topics: list[PipelineTopic],
    dfs: DataForSEOClient,
    embed_fn,
    # expansion (§7.3/§7.5)
    keyword_ideas_limit: int = 1000,
    keyword_suggestions_limit: int = 500,
    query_fanouts_limit: int = 300,
    paa_tier1_seeds: int = 8,
    paa_tier2_cap: int = 40,
    autocomplete_max: int = 1500,
    expansion_max_workers: int = 8,
    expansion_time_budget_s: float = 240.0,
    # competitor mining (§7.4)
    competitor_top_n: int = 5,
    ranked_keywords_limit: int = 500,
    competitor_max_position: int = 20,
    competitor_max_workers: int = 8,
    competitor_time_budget_s: float = 240.0,
    # relevance gate (§7.6) + clustering (§7.9)
    relevance_threshold: float = 0.62,
    relevance_embed_batch: int = 1000,
    clustering_edge_threshold: float = 0.55,
) -> PipelineResult:
    result = PipelineResult()
    topic_names = {t.id: t.name for t in topics}
    topic_embeddings = {t.id: t.embedding for t in topics}

    # ----- 1. Expansion (+ autocomplete) -----------------------------------
    exp = run_expansion(
        seed=seed,
        topics=[ExpansionTopic(id=t.id, anchor=build_anchor(seed, t.name), name=t.name)
                for t in topics],
        dfs=dfs,
        keyword_ideas_limit=keyword_ideas_limit,
        keyword_suggestions_limit=keyword_suggestions_limit,
        query_fanouts_limit=query_fanouts_limit,
        paa_tier1_seeds=paa_tier1_seeds,
        paa_tier2_cap=paa_tier2_cap,
        autocomplete_max=autocomplete_max,
        max_workers=expansion_max_workers,
        time_budget_s=expansion_time_budget_s,
    )
    result.degraded_notes.extend(exp.degraded_notes)
    result.timed_out = result.timed_out or exp.timed_out

    # Merge pools (keyword -> set of sources) per topic.
    pools: dict[str, dict[str, set[str]]] = {t.id: {} for t in topics}
    _merge(pools, exp.per_topic)

    # ----- 2. Competitor mining (gated silos + the always-mined seed) ------
    gated = [t for t in topics if t.gated]
    if gated:
        cm = run_competitor_mining(
            topics=[MineTopic(id=t.id, anchor=build_anchor(seed, t.name), name=t.name)
                    for t in gated],
            dfs=dfs,
            top_n=competitor_top_n,
            ranked_keywords_limit=ranked_keywords_limit,
            max_position=competitor_max_position,
            max_workers=competitor_max_workers,
            time_budget_s=competitor_time_budget_s,
        )
        result.degraded_notes.extend(cm.degraded_notes)
        result.timed_out = result.timed_out or cm.timed_out
        _merge(pools, cm.per_topic)

    # The seed itself is always mined (§7.2); its competitor keywords fan to
    # every silo, and the relevance gate sorts them per-silo.
    seed_cm = run_competitor_mining(
        topics=[MineTopic(id=_SEED_MINE_ID, anchor=seed, name=seed)],
        dfs=dfs,
        top_n=competitor_top_n,
        ranked_keywords_limit=ranked_keywords_limit,
        max_position=competitor_max_position,
        max_workers=competitor_max_workers,
        time_budget_s=competitor_time_budget_s,
    )
    result.degraded_notes.extend(seed_cm.degraded_notes)
    result.timed_out = result.timed_out or seed_cm.timed_out
    seed_keywords = seed_cm.per_topic.get(_SEED_MINE_ID, {})
    if seed_keywords:
        fanned = {t.id: seed_keywords for t in topics}
        _merge(pools, fanned)

    # ----- 3. Relevance gate + junk filter ---------------------------------
    per_topic_lists = {
        tid: {kw: sorted(sources) for kw, sources in kws.items()}
        for tid, kws in pools.items()
    }
    gate = run_relevance_gate(
        per_topic=per_topic_lists,
        topic_embeddings=topic_embeddings,
        embed_fn=embed_fn,
        topic_names=topic_names,
        threshold=relevance_threshold,
        batch_size=relevance_embed_batch,
    )
    result.degraded_notes.extend(gate.degraded_notes)
    result.per_topic_gated = gate.per_topic

    # ----- 4. Statistical clustering on the survivors ----------------------
    active_keywords: dict[str, list[str]] = {}
    active_embeddings: dict[str, list[list[float]]] = {}
    for tid, gated_kws in gate.per_topic.items():
        kws: list[str] = []
        embs: list[list[float]] = []
        for g in gated_kws:
            if g.status == "active" and g.embedding is not None:
                kws.append(g.keyword)
                embs.append(g.embedding)
        active_keywords[tid] = kws
        active_embeddings[tid] = embs

    cluster = run_clustering(
        per_topic_keywords=active_keywords,
        per_topic_embeddings=active_embeddings,
        edge_threshold=clustering_edge_threshold,
    )
    result.clustering_log = cluster.to_log()

    logger.info(
        "step_complete",
        extra={"event": "step_complete", "step": "refinement_pipeline",
               **result.counts(), "degraded": bool(result.degraded_notes),
               "timed_out": result.timed_out},
    )
    return result
