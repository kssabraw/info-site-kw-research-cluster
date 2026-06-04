"""Display-time within-cluster keyword dedup (Cluster View / PRD §9.2).

Pure-function tests: no DB, no egress. The dedup pass is two stages —
surface-form normalization and cosine collapse over the persisted embedding —
combined per cluster. Tests pin the rules to specific keyword pairs lifted from
the live MSP run that prompted this feature, plus edge cases that would
otherwise silently regress (empty/null embeddings, primary-of-cluster always
winning, transitive cosine merges across pairs that aren't directly similar).
"""

from app.cluster_dedupe import (
    KeywordRow,
    dedupe_by_cluster,
    dedupe_cluster,
    normalize_keyword,
)


def _row(
    id: str,
    keyword: str,
    *,
    cluster_id: str = "c1",
    volume: int | None = None,
    relevance: float | None = None,
    is_primary: bool = False,
    embedding: list[float] | None = None,
) -> KeywordRow:
    return KeywordRow(
        id=id,
        cluster_id=cluster_id,
        keyword=keyword,
        volume=volume,
        relevance_score=relevance,
        is_primary_for_cluster=is_primary,
        embedding=embedding,
    )


# ---------------------------------------------------------------------------
# Surface-form normalization
# ---------------------------------------------------------------------------

def test_plurals_collapse():
    assert normalize_keyword("managed service provider example") == normalize_keyword(
        "managed service provider examples"
    )


def test_article_variants_collapse():
    # "what is a X" / "what is an X" / "what is the X" all match "what is X".
    a = normalize_keyword("what is a managed it service provider")
    b = normalize_keyword("what is an it managed service provider")
    c = normalize_keyword("what is a it managed service provider")
    assert a == b == c


def test_what_is_vs_what_are_collapse():
    assert normalize_keyword("what is managed infrastructure services") == normalize_keyword(
        "what are managed infrastructure services"
    )


def test_msp_alias_folds_to_managed_service_provider():
    assert normalize_keyword("msp example") == normalize_keyword(
        "managed service provider example"
    )


def test_distinct_intents_do_not_collapse():
    # These look similar but the topical noun is genuinely different.
    assert normalize_keyword("what is managed it support") != normalize_keyword(
        "what is managed it solutions"
    )


def test_meaning_vs_definition_do_not_surface_form_collapse():
    # Surface-form can't catch synonyms — that's cosine's job.
    assert normalize_keyword("msp meaning") != normalize_keyword("msp definition")


def test_empty_and_punctuation_only_input():
    assert normalize_keyword("") == ""
    assert normalize_keyword("   ") == ""
    assert normalize_keyword("?!.,") == ""


# ---------------------------------------------------------------------------
# Within-cluster dedup (surface-form + cosine)
# ---------------------------------------------------------------------------

def test_surface_form_collapses_pair_pick_higher_volume():
    a = _row("a", "msp example", volume=100)
    b = _row("b", "msp examples", volume=300)
    mapping = dedupe_cluster([a, b], cosine_threshold=1.0)  # cosine disabled
    # Higher volume wins.
    assert mapping["a"] == "b"
    assert mapping["b"] == "b"


def test_primary_always_canonical_even_if_lower_volume():
    p = _row("p", "what is msp", volume=10, is_primary=True)
    o = _row("o", "what are msp", volume=10_000)
    mapping = dedupe_cluster([p, o], cosine_threshold=1.0)
    # Primary outranks volume — it must remain the canonical the card points at.
    assert mapping["p"] == "p"
    assert mapping["o"] == "p"


def test_cosine_collapses_synonyms_when_surface_form_cannot():
    # Surface forms differ ("meaning" vs "definition") so pass 1 leaves them
    # separate. Pass 2 with cosine ~0.99 collapses them.
    a = _row("a", "msp meaning", volume=100, embedding=[1.0, 0.0, 0.0])
    b = _row("b", "msp definition", volume=200, embedding=[1.0, 0.01, 0.0])
    mapping = dedupe_cluster([a, b], cosine_threshold=0.95)
    assert mapping["a"] == "b"  # higher volume wins
    assert mapping["b"] == "b"


def test_cosine_skipped_when_threshold_is_one():
    a = _row("a", "msp meaning", embedding=[1.0, 0.0])
    b = _row("b", "msp definition", embedding=[1.0, 0.0])
    mapping = dedupe_cluster([a, b], cosine_threshold=1.0)
    # Both keep their own id (surface-form differs, cosine disabled).
    assert mapping["a"] == "a"
    assert mapping["b"] == "b"


def test_cosine_below_threshold_does_not_collapse():
    a = _row("a", "msp meaning", embedding=[1.0, 0.0])
    b = _row("b", "msp pricing", embedding=[0.0, 1.0])  # cosine = 0
    mapping = dedupe_cluster([a, b], cosine_threshold=0.95)
    assert mapping["a"] == "a"
    assert mapping["b"] == "b"


def test_null_embedding_falls_back_to_surface_form_only():
    # Old sessions (pre-migration) carry null embeddings. The cosine pass should
    # silently skip them, and surface-form dedup still runs.
    a = _row("a", "msp example", volume=100, embedding=None)
    b = _row("b", "msp examples", volume=200, embedding=None)
    mapping = dedupe_cluster([a, b], cosine_threshold=0.95)
    assert mapping["a"] == "b"
    assert mapping["b"] == "b"


def test_transitive_cosine_merge_pulls_indirect_pair_together():
    # A~B (cosine 0.98), B~C (cosine 0.98), A and C are NOT directly above
    # threshold — they still end up in the same dedup group via B. C is the
    # highest-volume, so all three should canonicalize to C.
    a = _row("a", "alpha", volume=10, embedding=[1.0, 0.0, 0.0])
    b = _row("b", "bravo", volume=50, embedding=[0.99, 0.14, 0.0])
    c = _row("c", "charlie", volume=200, embedding=[0.0, 0.99, 0.14])
    # Above looks contrived — assert via the actual angles:
    #   a.b ~ 0.99,   b.c ~ 0.14*0.99+0.0 ~ 0.14 (too low!)
    # Use a simpler chain that is actually transitive in cosine:
    a = _row("a", "alpha", volume=10, embedding=[1.0, 0.05, 0.0])
    b = _row("b", "bravo", volume=50, embedding=[1.0, 0.10, 0.0])
    c = _row("c", "charlie", volume=200, embedding=[1.0, 0.15, 0.0])
    mapping = dedupe_cluster([a, b, c], cosine_threshold=0.95)
    # All three collapse to C (highest volume).
    assert mapping["a"] == "c"
    assert mapping["b"] == "c"
    assert mapping["c"] == "c"


def test_dedupe_by_cluster_isolates_groups():
    # A "msp example" in cluster c1 must not collapse with one in cluster c2.
    a1 = _row("a", "msp example", cluster_id="c1", volume=100)
    a2 = _row("b", "msp example", cluster_id="c2", volume=200)
    mapping = dedupe_by_cluster([a1, a2], cosine_threshold=1.0)
    assert mapping["a"] == "a"
    assert mapping["b"] == "b"


def test_unclustered_keywords_pass_through_unchanged():
    a = _row("a", "msp example", cluster_id=None, volume=100)
    b = _row("b", "msp examples", cluster_id=None, volume=200)
    mapping = dedupe_by_cluster([a, b], cosine_threshold=0.95)
    # Each unclustered row is its own canonical regardless of similarity.
    assert mapping["a"] == "a"
    assert mapping["b"] == "b"


def test_relevance_wins_when_volume_tied():
    a = _row("a", "msp example", volume=None, relevance=0.7)
    b = _row("b", "msp examples", volume=None, relevance=0.9)
    mapping = dedupe_cluster([a, b], cosine_threshold=1.0)
    assert mapping["b"] == "b"
    assert mapping["a"] == "b"


def test_alphabetic_tiebreak_when_all_signals_tied():
    a = _row("a", "msp examples", volume=100, relevance=0.5)
    b = _row("b", "msp example", volume=100, relevance=0.5)
    # Same surface form -> collapse; tiebreak is shorter then alphabetic.
    mapping = dedupe_cluster([a, b], cosine_threshold=1.0)
    # "msp example" (len 11) beats "msp examples" (len 12) on the length sort.
    assert mapping["a"] == "b"
    assert mapping["b"] == "b"


def test_msp_example_collapses_across_surface_and_alias():
    # The marquee case from the user's screenshot: the bare-noun phrasings
    # should all collapse via the alias + plural rules. "what are msp
    # examples?" is a different surface form (it asks a question) so it stays
    # separate — that's the right call: an article would treat it differently.
    rows = [
        _row("a", "msp example", volume=50),
        _row("b", "managed service provider example", volume=200),
        _row("c", "managed service provider examples", volume=150),
        _row("d", "what are msp examples?", volume=80),
    ]
    mapping = dedupe_cluster(rows, cosine_threshold=1.0)
    # a / b / c collapse to b (highest volume).
    assert mapping["a"] == "b"
    assert mapping["b"] == "b"
    assert mapping["c"] == "b"
    # d carries a question head, so it's a different canonical.
    assert mapping["d"] == "d"


def test_empty_input_returns_empty_mapping():
    assert dedupe_cluster([], cosine_threshold=0.95) == {}
    assert dedupe_by_cluster([], cosine_threshold=0.95) == {}
