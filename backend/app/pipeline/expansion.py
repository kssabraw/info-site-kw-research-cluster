"""Per-silo keyword expansion (PRD §7.3) + autocomplete enrichment (§7.5).

For each finalized silo, four DataForSEO endpoints run in parallel
(keyword_ideas, keyword_suggestions, query_fanouts, PAA two tiers deep). The
deduped keyword pool is then enriched via autocomplete. A failure on one
endpoint degrades that silo's pool but never blocks the others (§16.2).

M3 stops here: keywords are persisted raw with source attribution. Relevance
gating, competitor mining, and clustering are M4.
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from app.dataforseo import DataForSEOClient

logger = logging.getLogger(__name__)

# Connective/filler tokens stripped when deriving a tight phrase-match anchor
# from a silo name. We keep domain nouns (obesity, dosing, trials) and drop only
# words that would over-narrow a phrase-match query or add no topical signal.
_ANCHOR_STOPWORDS = frozenset({
    "and", "or", "the", "a", "an", "of", "for", "to", "in", "on", "at", "with",
    "your", "you", "use", "uses", "using", "how", "what", "why", "when", "who",
    "does", "do", "is", "are",
})


@dataclass
class ExpansionTopic:
    id: str
    anchor: str
    name: str = ""  # friendly silo name for UI messages; falls back to anchor
    # Tight, phrase-matchable anchor for the seed-sensitive endpoints
    # (keyword_suggestions, query_fanouts). Falls back to `anchor` when empty.
    suggest_anchor: str = ""


@dataclass
class ExpansionResult:
    # topic_id -> {normalized_keyword: sorted list of source tags}
    per_topic: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    degraded_notes: list[str] = field(default_factory=list)
    timed_out: bool = False  # hit the time budget (logged; not surfaced to the user)

    @property
    def total_keywords(self) -> int:
        return sum(len(kws) for kws in self.per_topic.values())


def _normalize(kw: str) -> str:
    return " ".join(kw.strip().lower().split())


def build_anchor(seed: str, silo_name: str) -> str:
    """Seed-qualify the expansion anchor so DataForSEO returns seed-relevant
    keywords. If the silo name already contains the seed (e.g. "how retatrutide
    works") it's used as-is; otherwise the seed is prepended (e.g. "weight loss
    use" -> "retatrutide weight loss use")."""
    seed = seed.strip()
    silo_name = silo_name.strip()
    if seed.lower() in silo_name.lower():
        return silo_name
    return f"{seed} {silo_name}".strip()


def build_tight_anchor(seed: str, silo_name: str) -> str:
    """A concise, phrase-matchable anchor for the seed-sensitive endpoints
    (keyword_suggestions, query_fanouts). Those endpoints only return keywords
    that *contain* the anchor, so a long descriptive anchor like
    "retatrutide Obesity & Metabolic Uses" matches nothing. We seed-qualify the
    first salient (non-filler) token of the silo name instead, e.g.
    "Obesity & Metabolic Uses" -> "retatrutide obesity". Falls back to the bare
    seed when the name yields no salient token."""
    seed = seed.strip()
    seed_tokens = set(seed.lower().split())
    for raw in re.split(r"[^0-9a-z]+", silo_name.lower()):
        tok = raw.strip()
        if not tok or tok in _ANCHOR_STOPWORDS or tok in seed_tokens:
            continue
        return f"{seed} {tok}"
    return seed


def _add(pool: dict[str, set[str]], keyword: str, source: str) -> None:
    if not isinstance(keyword, str):
        return  # tolerate a malformed (non-string) element in a source result
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
    time_budget_s: float = 240.0,
) -> ExpansionResult:
    result = ExpansionResult()
    deadline = time.monotonic() + time_budget_s
    capped = False
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
            except Exception:
                continue
        return tier1, tier2[:paa_tier2_cap]

    # ----- Phase 1: base expansion (parallel across topic x endpoint) -------
    # keyword_ideas (broad ideation) and PAA use the broad silo anchor; the
    # phrase/seed-sensitive endpoints use the tight anchor, since a long
    # descriptive anchor returns 0 from keyword_suggestions/query_fanouts.
    pool_exec = ThreadPoolExecutor(max_workers=max_workers)
    futures = {}
    for t in topics:
        tight = t.suggest_anchor or t.anchor
        jobs = [
            ("keyword_ideas", t.anchor,
             lambda a: dfs.keyword_ideas(a, keyword_ideas_limit)),
            ("keyword_suggestions", tight,
             lambda a: dfs.keyword_suggestions(a, keyword_suggestions_limit)),
            ("query_fanouts", tight,
             lambda a: dfs.query_fanouts(a, query_fanouts_limit)),
            ("paa", t.anchor, paa_two_tier),
        ]
        for source, anchor, fn in jobs:
            futures[pool_exec.submit(fn, anchor)] = (t, source)

    try:
        for fut in as_completed(futures, timeout=max(0.0, deadline - time.monotonic())):
            topic, source = futures[fut]
            try:
                data = fut.result()
            except Exception as exc:
                # Any failure (HTTP error, non-JSON body, unexpected result
                # shape) degrades this source only; the others still land (§16.2).
                label = topic.name or topic.anchor
                result.degraded_notes.append(
                    f"Partial expansion for silo “{label}”: {source} unavailable."
                )
                logger.warning(
                    "degraded",
                    extra={"event": "degraded", "step": "expansion",
                           "topic": label, "source": source, "reason": str(exc)},
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
    except TimeoutError:
        # Hit the overall time budget. Keep what completed; abandon the rest.
        capped = True
    finally:
        pool_exec.shutdown(wait=False, cancel_futures=True)

    # ----- Phase 2: autocomplete on the deduped pool (§7.5) -----------------
    # (topic_id, keyword) pairs, capped globally to bound cost. Interleave
    # round-robin across topics so the cap is shared fairly (a large first silo
    # doesn't starve later silos of autocomplete).
    per_topic_keys = [(tid, list(kws.keys())) for tid, kws in pools.items()]
    seeds: list[tuple[str, str]] = []
    longest = max((len(ks) for _, ks in per_topic_keys), default=0)
    for i in range(longest):
        if len(seeds) >= autocomplete_max:
            break
        for tid, ks in per_topic_keys:
            if i < len(ks):
                seeds.append((tid, ks[i]))
    seeds = seeds[:autocomplete_max]

    # Only enrich if the time budget hasn't already been spent on base expansion.
    if seeds and not capped and (deadline - time.monotonic()) > 1.0:
        ok = 0
        fail = 0
        ac_additions: list[tuple[str, str]] = []
        ac_exec = ThreadPoolExecutor(max_workers=max_workers)
        ac_futures = {ac_exec.submit(dfs.autocomplete, kw): tid for tid, kw in seeds}
        try:
            for fut in as_completed(ac_futures, timeout=max(0.0, deadline - time.monotonic())):
                tid = ac_futures[fut]
                try:
                    suggestions = fut.result()
                    ok += 1
                except Exception:
                    fail += 1
                    continue
                for sug in suggestions:
                    ac_additions.append((tid, sug))
        except TimeoutError:
            capped = True
        finally:
            ac_exec.shutdown(wait=False, cancel_futures=True)

        # On a clean finish, skip autocomplete entirely if a majority failed
        # (§16.2). On a time-cap, keep whatever completed.
        if not capped and fail and fail / (ok + fail) > 0.5:
            result.degraded_notes.append("Autocomplete enrichment unavailable for this run.")
        else:
            for tid, sug in ac_additions:
                _add(pools[tid], sug, "autocomplete")
    elif seeds and (capped or (deadline - time.monotonic()) <= 1.0):
        capped = True

    if capped:
        result.timed_out = True
        logger.info("step_capped", extra={"event": "step_capped", "step": "expansion"})

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
