"""M12 SIE — pure-function tests for the noise layers (extract) and the n-gram /
aggregation / subsumption / coverage logic (ngrams). No bs4/spaCy needed: the
lemmatizer is injected and the cross-page/heuristic/frequency layers are pure.

Runnable two ways: `pytest tests/test_sie_pure.py` (CI) or `python tests/test_sie_pure.py`
(sandbox, no pytest)."""

from app.sie.extract import (
    Zones, ZonePage,
    cross_page_fingerprint, frequency_anomaly_terms, heuristic_keep,
    is_cta, is_service_area_list, normalize_block,
)
from app.sie.ngrams import AggregatedTerm, ZoneStat, aggregate_pages, coverage_gate, make_ngrams, subsume
from app.sie.filters import compute_tfidf, tfidf_gate
from app.sie.scoring import (
    _safe_exclude_outliers, minmax_normalize, percentile, quadgram_zone_multiplier,
    recommend_word_count, score_terms, usage_range,
)

# A trivial lemmatizer for tests: lowercase split, mark a few stopwords.
_STOPS = {"how", "to", "a", "the", "is", "of", "for"}
def _lemma(text):
    return [(w.lower().strip(".,"), w.lower().strip(".,") in _STOPS) for w in text.split() if w.strip(".,")]


def _page(url, *, h2=None, paragraphs=None, rank=None, title=""):
    return ZonePage(
        url=url, domain=url.split("//")[-1].split("/")[0], rank=rank,
        word_count=100,
        zones=Zones(title=title, h2=h2 or [], paragraphs=paragraphs or []),
    )


# ----- Layer 3: cross-page fingerprint --------------------------------------

def test_cross_page_fingerprint_flags_3plus_domains():
    boiler = "Licensed bonded and insured"
    pages = [
        _page("https://a.com", paragraphs=[boiler, "We repair tankless water heaters fast"]),
        _page("https://b.com", paragraphs=[boiler, "Our team installs gas water heaters"]),
        _page("https://c.com", paragraphs=[boiler, "Electric water heater replacement service"]),
    ]
    flagged = cross_page_fingerprint(pages, min_domains=3)
    assert normalize_block(boiler) in flagged
    assert normalize_block("We repair tankless water heaters fast") not in flagged


def test_cross_page_fingerprint_two_domains_not_flagged():
    b = "Call us for a free estimate"
    pages = [_page("https://a.com", paragraphs=[b]), _page("https://b.com", paragraphs=[b])]
    assert normalize_block(b) not in cross_page_fingerprint(pages, min_domains=3)


# ----- Layer 4: heuristic filters -------------------------------------------

def test_heuristic_keep_rejects_short_cta_service_area():
    assert heuristic_keep("Too short")[0] is False              # <5 words
    keep, reason = heuristic_keep("Call us today for a quote")
    assert keep is False and reason == "cta_pattern"
    assert is_cta("schedule your appointment now")
    assert is_service_area_list("Brooklyn Queens Manhattan Bronx Staten")
    keep, _ = heuristic_keep("water heater repair is affordable and reliable today")
    assert keep is True


# ----- Layer 5: frequency anomaly -------------------------------------------

def test_frequency_anomaly_flags_constant_term():
    flagged = frequency_anomaly_terms(
        {"licensed bonded insured": [2, 2, 2, 2, 2], "water heater": [1, 3, 2, 5, 1]},
        min_pages=4, cv_threshold=0.1,
    )
    assert "licensed bonded insured" in flagged    # zero variance
    assert "water heater" not in flagged           # organic variance


def test_frequency_anomaly_needs_min_pages():
    assert frequency_anomaly_terms({"x": [2, 2, 2]}, min_pages=4) == set()


# ----- Module 7: n-grams -----------------------------------------------------

def test_make_ngrams_stopwords_unigrams_only():
    grams = make_ngrams(_lemma("how to repair a heater"))
    assert "how" not in grams[1] and "to" not in grams[1]    # stopwords dropped from unigrams
    assert "repair" in grams[1] and "heater" in grams[1]
    assert "how to repair" in grams[3]                       # but kept inside trigrams
    assert grams[2][0] == "how to"


# ----- Module 8: aggregation + quadgram flag --------------------------------

def test_aggregate_and_quadgram_zone_flag():
    pages = [
        _page("https://a.com", h2=["emergency water heater repair service"]),
        _page("https://b.com", h2=["emergency water heater repair service"]),
    ]
    terms = aggregate_pages(pages, _lemma, boilerplate=set())
    quad = terms["emergency water heater repair"]
    assert quad.pages_found == 2 and quad.n == 4
    assert quad.quadgram_zone_flag is True                   # H2 on 2 pages


# ----- Module 8: subsumption ------------------------------------------------

def test_subsume_contiguous_contained_same_zone():
    pages = [
        _page("https://a.com", h2=["water heater repair cost"]),
        _page("https://b.com", h2=["water heater repair cost"]),
    ]
    terms = aggregate_pages(pages, _lemma, boilerplate=set())
    assert "water heater" in terms and "water heater repair cost" in terms
    survivors = subsume(terms, target_keyword=None)
    assert "water heater repair cost" in survivors
    assert "water heater" not in survivors                   # folded into the quadgram
    assert "water heater" in survivors["water heater repair cost"].subsumed_terms


def test_subsume_never_target_subphrase():
    pages = [_page(f"https://{d}.com", h2=["water heater repair cost"]) for d in "ab"]
    terms = aggregate_pages(pages, _lemma, boilerplate=set())
    survivors = subsume(terms, target_keyword="water heater")
    assert "water heater" in survivors                       # protected as target sub-phrase


def test_subsume_independent_coverage_kept():
    pages = [
        _page("https://a.com", h2=["water heater repair cost"]),
        _page("https://b.com", h2=["water heater repair cost"]),
        _page("https://c.com", h2=["water heater"]),          # shorter on an extra page
    ]
    terms = aggregate_pages(pages, _lemma, boilerplate=set())
    survivors = subsume(terms, target_keyword=None)
    assert "water heater" in survivors                       # independent coverage -> not subsumed


# ----- Module 8: coverage gate ----------------------------------------------

def test_coverage_gate_threshold_and_exceptions():
    pages = [_page(f"https://d{i}.com", rank=i + 1, paragraphs=["x"]) for i in range(10)]
    terms = aggregate_pages(
        [_page(f"https://d{i}.com", rank=i + 1, paragraphs=["solar water heater rebate program available now"])
         for i in range(3)], _lemma, boilerplate=set(),
    )
    coverage_gate(terms, pages, threshold=3)
    # "solar water" appears on 3 pages -> passes; a 1-page term would be low_coverage.
    assert terms["solar water"].passes_coverage is True

    # rank 1-3 only from 2+ domains exception
    rp = [_page("https://a.com", rank=1, paragraphs=["niche rare phrase here indeed"]),
          _page("https://b.com", rank=2, paragraphs=["niche rare phrase here indeed"])]
    rt = aggregate_pages(rp, _lemma, boilerplate=set())
    coverage_gate(rt, rp + [_page("https://c.com", rank=4)], threshold=3)
    assert rt["niche rare"].passes_coverage is True
    assert rt["niche rare"].coverage_exception == "rank 1-3 only, 2+ unique domains"


def _zp(url, wc):
    return ZonePage(url=url, domain=url, zones=Zones(), word_count=wc)


def _term(term, n=2, **kw):
    t = AggregatedTerm(term=term, n=n)
    for k, v in kw.items():
        setattr(t, k, v)
    return t


# ----- Module 9: TF-IDF ------------------------------------------------------

def test_tfidf_idf_zero_for_ubiquitous_term_and_gate():
    pages = [_zp(f"https://{d}.com", 100) for d in "abc"]
    terms = {
        "rare": _term("rare", per_page_count={"https://a.com": 5}, pages={"https://a.com"}),
        "common": _term("common", per_page_count={u.url: 5 for u in pages},
                        pages={u.url for u in pages}),
    }
    compute_tfidf(terms, pages)
    assert terms["common"].tfidf == 0.0            # on every page -> idf 0
    assert terms["rare"].tfidf > 0.005
    tfidf_gate(terms)
    assert terms["rare"].passes_tfidf is True and terms["common"].passes_tfidf is False


def test_tfidf_gate_preserves_coverage_exception():
    t = _term("niche", tfidf=0.0, coverage_exception="rank 1-3 only, 2+ unique domains")
    tfidf_gate({"niche": t})
    assert t.passes_tfidf is True                  # exception overrides low tfidf


# ----- Module 12: word count -------------------------------------------------

def test_recommend_word_count_filters_and_percentiles():
    pages = [_zp("u", w) for w in (500, 900, 1500, 2000, 6000)]
    lo, target, hi, src = recommend_word_count(pages)
    assert src == [900, 1500, 2000]                # 500/6000 filtered out
    assert target == 1500 and lo <= target <= hi


# ----- Module 13: scoring ----------------------------------------------------

def test_minmax_and_percentile():
    assert minmax_normalize([5, 5, 5]) == [0.5, 0.5, 0.5]    # all-equal rule
    assert minmax_normalize([0, 10])[0] == 0.0 and minmax_normalize([0, 10])[1] == 1.0
    assert percentile([1, 2, 3, 4], 0.5) == 2.5


def test_quadgram_multiplier_and_boost():
    quad = _term("a b c d", n=4, pages={"u1", "u2"},
                 zones={"h2": ZoneStat(total_count=2, pages={"u1", "u2"})})
    assert quadgram_zone_multiplier(quad) == 1.4
    bigram = _term("e f", n=2, pages={"u1"}, zones={"paragraphs": ZoneStat(pages={"u1"})})
    score_terms([quad, bigram], rank_by_url={"u1": 1, "u2": 2})
    assert quad.zone_boost_applied is True and bigram.zone_boost_applied is False


# ----- Module 14: usage recommendations -------------------------------------

def test_safe_mode_excludes_3x_median_outlier():
    freqs = [2.0] * 9 + [18.0]
    kept = _safe_exclude_outliers(freqs)
    assert 18.0 not in kept and kept.count(2.0) == 9


def test_usage_range_safe_vs_aggressive_and_cap():
    wc = {f"u{i}": 1000 for i in range(10)}
    zpc = {f"u{i}": 2 for i in range(9)}
    zpc["u9"] = 18
    t = _term("x", zone_page_count={"paragraphs": zpc})
    safe = usage_range(t, "paragraphs", 1000, wc, mode="safe")
    aggressive = usage_range(t, "paragraphs", 1000, wc, mode="aggressive")
    assert safe[2] == 2                            # outlier excluded -> max 2
    assert aggressive[2] >= safe[2]                # outlier inflates aggressive
    # 10-per-1000 cap: a term used 50x/1000 words caps at 10 at target 1000 wc.
    hot = _term("y", zone_page_count={"paragraphs": {f"u{i}": 50 for i in range(5)}})
    assert usage_range(hot, "paragraphs", 1000, {f"u{i}": 1000 for i in range(5)})[2] == 10


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"PASS — {len(fns)} pure-function tests")


if __name__ == "__main__":
    _run_all()
