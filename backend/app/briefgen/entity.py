"""Brief Generator Step 3.6 — main-entity derivation (M13 slice 3, X.2).

Derives the single main entity (the noun phrase the AIO answer repeatedly names, in
its preferred surface form) for the heading-form pass, the residual restatement gate,
and MCS rephrase suggestions (aio-optimization-plan.md §13.X.8).

Design mirrors SIE: the spaCy-dependent step is a boundary (`NounPhrase` extraction —
noun chunks + head lemma + grammatical-subject + org-NER tags); the scoring /
clustering / confidence logic is PURE and fixture-testable without spaCy. The only
embedding calls (sanity check + low-confidence title tie-break + title fallback) use
`text-embedding-3-large` (brief-plan §7 #3 / aio §0 #1), injected as `embed_fn`.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

# Confidence + sanity thresholds (aio §13.X.8).
CONFIDENCE_ACCEPT = 1.5            # winner/runner-up score ratio to accept the AIO entity
MIN_WINNER_FREQUENCY = 3          # below this the frequency signal is unreliable
KEYWORD_SANITY_COSINE = 0.45      # winner must be >= this cosine to the primary keyword
TITLE_TIEBREAK_MARGIN = 0.10      # within this title-cosine margin -> title fallback
SUBJECT_WEIGHT = 1.5             # grammatical-subject mentions count more
GENERIC_HEAD_PENALTY = 0.5       # single-token generic head with no modifier


@dataclass
class NounPhrase:
    """One noun-phrase occurrence (the spaCy boundary). `norm` is the counting form
    (lowercased, head noun lemmatized); `raw` is the surface form as written (the
    canonical output preserves it)."""

    raw: str
    norm: str
    head_lemma: str
    is_subject: bool = False
    is_org: bool = False


@dataclass
class MainEntity:
    canonical: str
    variants: list[str] = field(default_factory=list)
    source: str = "title_fallback"          # "aio" | "title_fallback"
    confidence: float = 0.0
    multi_entity_flag: bool = False
    secondary_entity: str | None = None
    emq_identical: bool = False


EmbedFn = Callable[[list[str]], list[list[float]]]
NpExtractor = Callable[[str], list[NounPhrase]]


def cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


# ----- pure clustering + scoring --------------------------------------------


@dataclass
class _Cluster:
    head_lemma: str
    raws: Counter                 # raw surface form -> count
    count: int = 0               # total mentions
    subject_count: int = 0       # mentions that were grammatical subjects
    norms: set[str] = field(default_factory=set)

    @property
    def canonical(self) -> str:
        return self.raws.most_common(1)[0][0]

    @property
    def variants(self) -> list[str]:
        return [r for r, _ in self.raws.most_common() if r != self.canonical]

    @property
    def single_token(self) -> bool:
        # generic head with no modifier == every member norm is a single token.
        return all(len(n.split()) == 1 for n in self.norms)

    @property
    def score(self) -> float:
        weighted = self.subject_count * SUBJECT_WEIGHT + (self.count - self.subject_count)
        spec = GENERIC_HEAD_PENALTY if self.single_token else 1.0
        return weighted * spec


def _mergeable(a_norm: str, b_norm: str, a_head: str, b_head: str) -> bool:
    """Token-set equal, OR one is a strict token-superstring of the other with the
    same head noun (aio §13.X.8 variant clustering). A *bare single-token* phrase is
    NOT absorbed into a longer superstring — that keeps a generic head ("benefits")
    its own candidate so the specificity penalty can demote it rather than the longer,
    specific phrase inheriting its frequency."""
    at, bt = set(a_norm.split()), set(b_norm.split())
    if at == bt:
        return True
    if a_head != b_head:
        return False
    if (at > bt or bt > at) and min(len(at), len(bt)) >= 2:
        return True
    return False


def cluster_phrases(phrases: list[NounPhrase]) -> list[_Cluster]:
    """Group occurrences by exact norm, then greedily merge norm-groups into variant
    clusters. Brand/org phrases are excluded (they're not the article's entity)."""
    groups: dict[str, _Cluster] = {}
    for p in phrases:
        if p.is_org or not p.norm.strip():
            continue
        g = groups.get(p.norm)
        if g is None:
            g = _Cluster(head_lemma=p.head_lemma, raws=Counter(), norms={p.norm})
            groups[p.norm] = g
        g.raws[p.raw] += 1
        g.count += 1
        if p.is_subject:
            g.subject_count += 1

    clusters: list[_Cluster] = []
    for norm, g in groups.items():
        placed = False
        for c in clusters:
            if any(_mergeable(norm, cn, g.head_lemma, c.head_lemma) for cn in c.norms):
                c.raws.update(g.raws)
                c.count += g.count
                c.subject_count += g.subject_count
                c.norms.add(norm)
                placed = True
                break
        if not placed:
            clusters.append(g)
    return clusters


# ----- derivation orchestration ---------------------------------------------


def derive_main_entity(
    *, aio_answer: str, aio_present: bool, title: str, keyword: str,
    np_extract: NpExtractor, embed_fn: EmbedFn,
    comparison_intent: bool = False,
) -> MainEntity:
    """Main-entity derivation (aio §13.X.8). Always returns a populated MainEntity —
    the title fallback exists by construction (Step-3.5 titles contain the keyword),
    so this never hard-fails and the heading-form pass is never skipped."""
    if aio_present and aio_answer.strip():
        clusters = cluster_phrases(np_extract(aio_answer))
        if clusters:
            ranked = sorted(clusters, key=lambda c: c.score, reverse=True)
            winner = ranked[0]
            runner = ranked[1] if len(ranked) > 1 else None
            confidence = winner.score / runner.score if runner and runner.score else float("inf")
            low_conf = confidence < CONFIDENCE_ACCEPT or winner.count < MIN_WINNER_FREQUENCY

            kw_vec = embed_fn([keyword])[0]

            chosen, secondary = winner, None
            if low_conf and runner is not None:
                # Tie-break the top two by title alignment (3-large).
                tvec, w_vec, r_vec = _embed3(embed_fn, title, winner.canonical, runner.canonical)
                cw, cr = cosine(w_vec, tvec), cosine(r_vec, tvec)
                chosen = winner if cw >= cr else runner
                secondary = (runner if chosen is winner else winner).canonical
                if abs(cw - cr) <= TITLE_TIEBREAK_MARGIN and not comparison_intent:
                    return _title_fallback(title, keyword, np_extract, embed_fn)

            # Sanity: the chosen entity must be on-topic vs the keyword (always checked).
            if cosine(embed_fn([chosen.canonical])[0], kw_vec) < KEYWORD_SANITY_COSINE:
                return _title_fallback(title, keyword, np_extract, embed_fn)

            return MainEntity(
                canonical=chosen.canonical, variants=chosen.variants, source="aio",
                confidence=(confidence if confidence != float("inf") else 99.0),
                multi_entity_flag=low_conf,
                secondary_entity=secondary if (low_conf or comparison_intent) else None,
                emq_identical=chosen.canonical.lower() == keyword.lower(),
            )

    return _title_fallback(title, keyword, np_extract, embed_fn)


def _embed3(embed_fn: EmbedFn, *texts: str) -> list[list[float]]:
    return embed_fn(list(texts))


def _title_fallback(
    title: str, keyword: str, np_extract: NpExtractor, embed_fn: EmbedFn
) -> MainEntity:
    """Noun-phrase chunk the title, take the chunk with highest cosine to the keyword.
    Always resolvable (the title contains the keyword)."""
    chunks = [p.raw for p in np_extract(title)] or [title.strip() or keyword]
    vecs = embed_fn([keyword, *chunks])
    kw_vec, chunk_vecs = vecs[0], vecs[1:]
    best = max(zip(chunks, chunk_vecs), key=lambda cv: cosine(cv[1], kw_vec))[0]
    return MainEntity(
        canonical=best, variants=[], source="title_fallback", confidence=0.0,
        emq_identical=best.lower() == keyword.lower(),
    )


_NLP = None


def build_np_extractor() -> NpExtractor:
    """Real spaCy boundary (en_core_web_sm). Lazy so the pure scoring imports/tests
    without spaCy. Needs the FULL pipeline (parser for noun_chunks + subjects, NER for
    ORG/brand exclusion) — unlike SIE's lemmatizer, which disables both. Strips leading
    determiners/possessives + trailing punctuation; tags grammatical subjects + ORGs."""
    global _NLP
    if _NLP is None:
        import spacy

        _NLP = spacy.load("en_core_web_sm")
    nlp = _NLP

    _DET = {"the", "a", "an", "this", "that", "these", "those", "your", "my", "our", "its"}

    def extract(text: str) -> list[NounPhrase]:
        doc = nlp(text or "")
        org_spans = {e.text.lower() for e in doc.ents if e.label_ == "ORG"}
        out: list[NounPhrase] = []
        for chunk in doc.noun_chunks:
            tokens = [t for t in chunk if not t.is_punct]
            while tokens and tokens[0].lower_ in _DET:
                tokens = tokens[1:]
            if not tokens:
                continue
            raw = " ".join(t.text for t in tokens).strip()
            head = chunk.root
            norm = " ".join(
                (head.lemma_.lower() if t is head else t.lower_) for t in tokens
            )
            is_subject = chunk.root.dep_ in ("nsubj", "nsubjpass")
            is_org = raw.lower() in org_spans
            out.append(NounPhrase(raw=raw, norm=norm, head_lemma=head.lemma_.lower(),
                                  is_subject=is_subject, is_org=is_org))
        return out

    return extract
