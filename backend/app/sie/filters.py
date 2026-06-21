"""SIE Modules 9–10: TF-IDF pre-filter (M9, pure) + semantic filtering (M10).

This slice ships M9 (pure, sandbox-testable). M10 (embeddings) is added in the
egress slice — its `attach_semantic_similarity(terms, embed_fn, keyword)` will set
`term.semantic_similarity` (cosine to the keyword, 0.65 gate with dynamic 0.60/0.70
adjustment + heading-term preservation). Until then `semantic_similarity` stays 0.0
and scoring treats it as a normalized input.
"""

from __future__ import annotations

import math

from .ngrams import AggregatedTerm, ZonePage

TFIDF_THRESHOLD = 0.005


def compute_tfidf(
    terms: dict[str, AggregatedTerm], pages: list[ZonePage]
) -> dict[str, AggregatedTerm]:
    """Corpus TF-IDF per term (PRD M9), set on `term.tfidf`.

        tf(term, page)   = term_count_in_page / page_word_count
        idf(term)        = log(total_pages / pages_containing_term)
        corpus_tfidf     = mean over pages where the term appears of tf*idf
    """
    total_pages = len(pages)
    wc_by_url = {p.url: p.word_count for p in pages}
    for term in terms.values():
        if total_pages == 0 or term.pages_found == 0:
            term.tfidf = 0.0
            continue
        idf = math.log(total_pages / term.pages_found)
        per_page = []
        for url, count in term.per_page_count.items():
            wc = wc_by_url.get(url, 0)
            if wc > 0:
                per_page.append((count / wc) * idf)
        term.tfidf = (sum(per_page) / len(per_page)) if per_page else 0.0
    return terms


def tfidf_gate(
    terms: dict[str, AggregatedTerm], *, threshold: float = TFIDF_THRESHOLD
) -> dict[str, AggregatedTerm]:
    """Set `passes_tfidf`. Below threshold fails, EXCEPT terms that passed a
    coverage exception (M8) or are quadgrams in title/H1/H2 on 2+ pages — those
    are always preserved (PRD M9 'Default Thresholds')."""
    for term in terms.values():
        if term.tfidf >= threshold:
            term.passes_tfidf = True
        elif term.coverage_exception or term.quadgram_zone_flag:
            term.passes_tfidf = True
        else:
            term.passes_tfidf = False
    return terms
