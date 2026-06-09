"""M6 site architecture tests (PRD §7.11): deterministic pillar editorial fields
(no LLM — the writer owns title/summary) + deterministic linking-matrix assembly +
the §15.2 acceptance rules (one pillar per silo, up-links, no orphans, ≤5
links/page, link-health audit)."""

from app.pipeline.architecture import (
    ArticleInput,
    PillarInput,
    run_architecture_generation,
)
from app.pipeline.architecture.generate import (
    _lateral_article_links,
    _lateral_pillar_links,
)
from app.pipeline.architecture.models import (
    ArchitectureResult,
    Pillar,
    SupportingArticle,
)


def _article(aid: str, name: str, peers=None) -> ArticleInput:
    return ArticleInput(
        id=aid, name=name, primary_keyword=name, intent="informational",
        peer_article_links=peers or [],
    )


def _pillar(tid: str, name: str, articles) -> PillarInput:
    return PillarInput(
        topic_id=tid, silo_name=name, rationale="why",
        relationship_type="use_case", articles=articles,
    )


# ---- run_architecture_generation: structure & acceptance criteria ----------


def test_one_pillar_per_silo_with_uplinks_and_no_orphans():
    pillars_in = [
        _pillar("t1", "Dosage", [_article("c1", "low dose"), _article("c2", "high dose")]),
        _pillar("t2", "Safety", [_article("c3", "side effects")]),
    ]
    result = run_architecture_generation(
        seed="retatrutide",
        audience="patients",
        pillars_input=pillars_in,
        topic_embeddings={"t1": [1.0, 0.0], "t2": [0.0, 1.0]},  # orthogonal -> no link
        cluster_centroids={},
    )
    # #1: one pillar per accepted silo.
    assert {p.topic_id for p in result.pillars} == {"t1", "t2"}
    # Small silos (≤ the down-links cap of 3) still link DOWN to all their children.
    by_topic = {p.topic_id: p for p in result.pillars}
    assert set(by_topic["t1"].supporting_article_ids) == {"c1", "c2"}
    assert by_topic["t2"].supporting_article_ids == ["c3"]
    # #2: every supporting article links UP to its pillar.
    assert all(a.parent_pillar_topic_id for a in result.supporting_articles)
    parents = {a.article_id: a.parent_pillar_topic_id for a in result.supporting_articles}
    assert parents == {"c1": "t1", "c2": "t1", "c3": "t2"}
    # #3: no orphans — here every article is in its pillar's down-links (small silos).
    for a in result.supporting_articles:
        assert a.article_id in by_topic[a.parent_pillar_topic_id].supporting_article_ids


def test_large_silo_caps_pillar_links_and_keeps_no_orphans_via_cycle():
    # 6 articles > the pillar down-links cap (3), so the pillar can NOT link to all.
    arts = [_article(f"c{i}", f"art {i}") for i in range(6)]
    centroids = {
        "c0": [1.0, 0.0], "c1": [0.95, 0.05], "c2": [0.9, 0.1],
        "c3": [0.0, 1.0], "c4": [0.05, 0.95], "c5": [0.1, 0.9],
    }
    result = run_architecture_generation(
        seed="x", audience="", pillars_input=[_pillar("t1", "Big Silo", arts)],
        topic_embeddings={}, cluster_centroids=centroids,
    )
    pillar = result.pillars[0]
    # Pillar links down to only 3 children (capped), not all 6.
    assert len(pillar.supporting_article_ids) == 3
    assert set(pillar.supporting_article_ids) <= {a.id for a in arts}  # no dangling
    # Per-page ≤5-link budget holds on every page.
    assert len(pillar.supporting_article_ids) + len(pillar.lateral_pillar_links) <= 5
    for a in result.supporting_articles:
        assert 1 + len(a.lateral_article_links) <= 5  # 1 up-link + laterals
    # No orphans: every article receives ≥1 inbound link (from the pillar's
    # down-links OR another article's lateral cycle edge). The cycle guarantees the
    # latter for the children the pillar didn't link to.
    inbound: set[str] = set(pillar.supporting_article_ids)
    for a in result.supporting_articles:
        inbound.update(a.lateral_article_links)
    assert {a.article_id for a in result.supporting_articles} <= inbound


def test_silo_without_articles_is_skipped_not_a_childless_pillar():
    pillars_in = [_pillar("t1", "Dosage", [_article("c1", "low dose")])]
    result = run_architecture_generation(
        seed="x", audience="", pillars_input=pillars_in,
        topic_embeddings={}, cluster_centroids={},
        skipped_silos=["Empty Silo"],
    )
    assert [p.topic_id for p in result.pillars] == ["t1"]
    assert result.skipped_silos == ["Empty Silo"]


def test_pillar_editorial_is_a_deterministic_placeholder():
    # No LLM: the writer owns the pillar title + summary, so the pipeline leaves a
    # placeholder (title = silo name, empty summary) + a deterministic target keyword.
    result = run_architecture_generation(
        seed="x", audience="",
        pillars_input=[_pillar("t1", "Triple Agonist Drugs", [_article("c1", "a")])],
        topic_embeddings={}, cluster_centroids={},
    )
    p = result.pillars[0]
    assert p.title == "Triple Agonist Drugs"           # placeholder = silo name
    assert p.target_keyword == "triple agonist drugs"  # deterministic head term
    assert p.summary == ""                             # writer owns the summary
    assert p.h2_outline == []                          # writer owns the outline
    assert p.degraded is False


# ---- lateral pillar links (#4): cosine > threshold -------------------------


def test_lateral_pillar_links_only_above_threshold_and_symmetric():
    links = _lateral_pillar_links(
        ["t1", "t2", "t3"],
        {
            "t1": [1.0, 0.0],
            "t2": [0.99, 0.14],   # cosine to t1 ~0.99 > 0.55 -> linked
            "t3": [0.0, 1.0],     # orthogonal to t1 -> not linked
        },
        threshold=0.55,
        max_per_pillar=5,
    )
    assert links["t2"] == ["t1"]
    assert links["t1"] == ["t2"]   # symmetric (when each side has room under the cap)
    assert links["t3"] == []       # below threshold


def test_lateral_pillar_links_skip_silos_without_embeddings():
    links = _lateral_pillar_links(
        ["t1", "t2"], {"t1": [1.0, 0.0]}, threshold=0.55, max_per_pillar=5,
    )
    assert links == {"t1": [], "t2": []}


def test_lateral_pillar_links_caps_at_top_n_by_cosine():
    # Seven pillars all within the cosine threshold of t0; with max_per_pillar=5,
    # t0's outbound list keeps the FIVE closest peers (highest cosine) and drops
    # the bottom two. The owner-set "no page > 5 outbound internal links" rule
    # for pillar laterals lives here.
    # Vectors crafted so t0 -> t1..t7 cosines descend monotonically:
    #   t1 closest, t7 farthest (but still above threshold).
    pillar_ids = [f"t{i}" for i in range(8)]
    embeddings = {
        "t0": [1.0, 0.0],
        "t1": [1.00, 0.05],
        "t2": [1.00, 0.10],
        "t3": [1.00, 0.15],
        "t4": [1.00, 0.20],
        "t5": [1.00, 0.25],
        "t6": [1.00, 0.30],
        "t7": [1.00, 0.35],
    }
    links = _lateral_pillar_links(
        pillar_ids, embeddings, threshold=0.55, max_per_pillar=5,
    )
    # All seven peers exceed the cosine bar, but t0's list is capped to its
    # five closest (t1..t5). t6 and t7 are dropped from t0's outbound list.
    assert len(links["t0"]) == 5
    assert links["t0"] == ["t1", "t2", "t3", "t4", "t5"]
    # t6 and t7 still appear in the OTHER pillars' lists (their own caps allow
    # it), confirming the cap is per-pillar rather than a global edge drop.
    assert "t6" in links["t1"] or "t6" in links["t7"]


def test_lateral_pillar_links_cap_of_zero_disables_the_cap():
    # max_per_pillar=0 (or negative) returns every above-threshold peer — used
    # in code paths where the caller wants the raw graph (e.g. diagnostics).
    pillar_ids = [f"t{i}" for i in range(8)]
    embeddings = {f"t{i}": [1.0, i * 0.05] for i in range(8)}
    links = _lateral_pillar_links(
        pillar_ids, embeddings, threshold=0.55, max_per_pillar=0,
    )
    assert len(links["t0"]) == 7  # every other pillar above the threshold


# ---- lateral article links: prioritize peer links, fill by centroid --------


def test_lateral_article_links_prioritize_existing_peer_links():
    a = _article("c1", "a", peers=["c9"])  # c9 is a cross-silo dedup peer
    out = _lateral_article_links(
        a, same_silo_ids={"c1", "c2", "c3"},
        cluster_centroids={
            "c1": [1.0, 0.0], "c2": [0.9, 0.1], "c3": [0.2, 0.9],
        },
        max_links=3,
    )
    # Existing peer first, then nearest same-silo neighbors by centroid cosine.
    assert out[0] == "c9"
    assert out[1] == "c2"   # closer to c1 than c3
    assert "c1" not in out  # never links to itself
    assert len(out) <= 3


def test_lateral_article_links_capped_and_self_excluded():
    a = _article("c1", "a", peers=["c2", "c3", "c4", "c5"])
    out = _lateral_article_links(
        a, same_silo_ids={"c1"}, cluster_centroids={}, max_links=3
    )
    assert out == ["c2", "c3", "c4"]   # capped at max_links, in priority order


# ---- link_health: runtime no-orphan / no-dangling audit (§15.2 #3) ----------
def test_link_health_clean_on_a_normal_graph():
    # A real generation (multi-silo, 6-article silo) must report a perfectly
    # healthy graph: zero orphans, zero dangling links.
    pillars_in = [
        _pillar("t1", "Big", [_article(f"c{i}", f"art {i}") for i in range(6)]),
        _pillar("t2", "Small", [_article("d1", "solo")]),
    ]
    result = run_architecture_generation(
        seed="x", audience="", pillars_input=pillars_in,
        topic_embeddings={}, cluster_centroids={},
    )
    assert result.link_health() == {
        "orphan_articles": 0, "orphan_pillars": 0, "dangling_links": 0,
    }


def test_link_health_detects_orphan_and_dangling():
    # Hand-built broken graph: the pillar links only a1; a2 has no inbound at all
    # (orphan); a1's lateral points at a non-existent node (dangling).
    result = ArchitectureResult(seed_keyword="x", detected_audience="")
    result.pillars.append(Pillar(
        topic_id="t1", silo_name="S", title="T", target_keyword="k", summary="",
        h2_outline=[], supporting_article_ids=["a1"], lateral_pillar_links=[],
    ))
    result.supporting_articles.append(SupportingArticle(
        article_id="a1", name="A1", intent="informational",
        parent_pillar_topic_id="t1", lateral_article_links=["ghost"],
    ))
    result.supporting_articles.append(SupportingArticle(
        article_id="a2", name="A2", intent="informational",
        parent_pillar_topic_id="t1", lateral_article_links=[],
    ))
    health = result.link_health()
    assert health["orphan_articles"] == 1   # a2 has no inbound link
    assert health["dangling_links"] == 1    # a1 -> "ghost" targets a non-node
    assert health["orphan_pillars"] == 0    # t1 gets up-links from a1 + a2
