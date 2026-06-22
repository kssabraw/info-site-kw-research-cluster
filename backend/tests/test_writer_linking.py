"""M15 slice 1 — slugs + deterministic link injection (pure)."""

from app.writer.link_injector import LinkTarget, inject_links
from app.writer.models import ArticleItem
from app.writer.slugs import assign_slugs, slugify


# ----- slugs ----------------------------------------------------------------

def test_slugify_basics():
    assert slugify("Is Retatrutide a GLP-3 Drug?") == "is-retatrutide-a-glp-3-drug"
    assert slugify("  Multiple   Spaces & Symbols! ") == "multiple-spaces-symbols"
    assert slugify("") == "page"
    assert slugify("---") == "page"


def test_assign_slugs_dedups_and_is_stable():
    items = [("a", "Retatrutide Dosing"), ("b", "Retatrutide Dosing"), ("c", "Side Effects")]
    out = assign_slugs(items)
    assert out["a"] == "retatrutide-dosing"
    assert out["b"] == "retatrutide-dosing-2"      # dedup
    assert out["c"] == "side-effects"
    # idempotent: re-running with existing keeps the stable slugs + only fills new ones
    out2 = assign_slugs([*items, ("d", "Side Effects")], existing=out)
    assert out2["a"] == "retatrutide-dosing" and out2["b"] == "retatrutide-dosing-2"
    assert out2["d"] == "side-effects-2"


# ----- link injection -------------------------------------------------------

def _article():
    return [
        ArticleItem(order=1, level="H1", type="title", heading="Retatrutide Guide"),
        ArticleItem(order=2, level="none", type="intro", body="An overview of retatrutide."),
        ArticleItem(order=3, level="H2", type="content", heading="Dosing"),
        ArticleItem(order=4, level="none", type="content",
                    body="The retatrutide dosing schedule matters. See tirzepatide for contrast."),
        ArticleItem(order=5, level="H2", type="conclusion", heading="Conclusion"),
        ArticleItem(order=6, level="none", type="content", body="In summary, retatrutide is promising."),
    ]


def test_inject_links_inline_first_occurrence():
    targets = [LinkTarget(url="https://s.com/silo/tirzepatide", anchors=["tirzepatide"], title="Tirzepatide")]
    res = inject_links(_article(), targets)
    body = next(it.body for it in res.article if "tirzepatide" in (it.body or "").lower())
    assert "[tirzepatide](https://s.com/silo/tirzepatide)" in body
    assert res.linked == ["https://s.com/silo/tirzepatide"] and res.related == []


def test_inject_links_one_link_per_target_and_skips_headings():
    # "Dosing" appears in a heading (skipped) and "retatrutide dosing" in prose (linked once).
    targets = [LinkTarget(url="https://s.com/silo/dosing", anchors=["retatrutide dosing"], title="Dosing")]
    res = inject_links(_article(), targets)
    md_bodies = [it.body for it in res.article if it.body]
    joined = "\n".join(md_bodies)
    assert joined.count("(https://s.com/silo/dosing)") == 1     # exactly one wrap
    assert all(it.heading != "[Dosing]" for it in res.article)  # heading untouched


def test_inject_links_unmatched_goes_to_related_before_conclusion():
    targets = [LinkTarget(url="https://s.com/silo/no-anchor-here",
                          anchors=["nonexistent phrase"], title="Cagrilintide")]
    res = inject_links(_article(), targets)
    assert len(res.related) == 1
    rel_idx = next(i for i, it in enumerate(res.article) if it.heading == "Related Articles")
    concl_idx = next(i for i, it in enumerate(res.article) if it.type == "conclusion")
    assert rel_idx < concl_idx                                  # Related sits before conclusion
    rel_body = res.article[rel_idx + 1].body
    assert "[Cagrilintide](https://s.com/silo/no-anchor-here)" in rel_body


def test_inject_links_does_not_double_wrap_existing_link():
    article = [ArticleItem(order=1, level="none", type="content",
                           body="See [tirzepatide](https://other.com) already linked.")]
    targets = [LinkTarget(url="https://s.com/silo/tirzepatide", anchors=["tirzepatide"], title="T")]
    res = inject_links(article, targets)
    # the existing link is preserved; no anchor left to wrap -> goes to Related
    assert "[tirzepatide](https://other.com)" in res.article[0].body
    assert res.related and res.related[0].url == "https://s.com/silo/tirzepatide"


def test_inject_links_pillar_renders_in_this_guide_list():
    article = [
        ArticleItem(order=1, level="H1", type="title", heading="Retatrutide: The Complete Guide"),
        ArticleItem(order=2, level="none", type="intro", body="Everything about retatrutide."),
        ArticleItem(order=3, level="H2", type="content", heading="Background"),
        ArticleItem(order=4, level="none", type="content", body="Detail."),
    ]
    children = [LinkTarget(url="https://s.com/silo/dosing", anchors=["dosing"], title="Dosing"),
                LinkTarget(url="https://s.com/silo/side-effects", anchors=["side effects"], title="Side Effects")]
    res = inject_links(article, children, is_pillar=True)
    guide_idx = next(i for i, it in enumerate(res.article) if it.heading == "In This Guide")
    assert res.article[guide_idx + 1].body.count("](https://s.com/silo/") == 2
    assert set(res.linked) == {c.url for c in children}
    assert guide_idx > 0 and res.article[0].level == "H1"        # after H1/intro, not before


# ----- targets builder (architecture graph -> LinkTargets) ------------------

def _architecture():
    return {
        "pillars": [
            {"topic_id": "t1", "silo_name": "Retatrutide Basics", "title": "Retatrutide: Complete Guide",
             "target_keyword": "retatrutide", "supporting_article_ids": ["c1", "c2"], "lateral_pillar_links": []},
        ],
        "supporting_articles": [
            {"article_id": "c1", "name": "Retatrutide Dosing", "intent": "informational",
             "parent_pillar_topic_id": "t1", "lateral_article_links": ["c2"]},
            {"article_id": "c2", "name": "Retatrutide Side Effects", "intent": "informational",
             "parent_pillar_topic_id": "t1", "lateral_article_links": ["c1"]},
        ],
    }


def test_build_targets_supporting_article_uplink_and_lateral():
    from app.writer.link_targets import build_targets

    clusters_by_id = {
        "c1": {"id": "c1", "topic_id": "t1", "name": "Retatrutide Dosing", "primary_keyword_id": "k1", "slug": "retatrutide-dosing"},
        "c2": {"id": "c2", "topic_id": "t1", "name": "Retatrutide Side Effects", "primary_keyword_id": "k2", "slug": "retatrutide-side-effects"},
    }
    topics_by_id = {"t1": {"id": "t1", "name": "Retatrutide Basics"}}
    keywords_by_id = {"k1": "retatrutide dosing", "k2": "retatrutide side effects"}

    targets, is_pillar = build_targets(
        "c1", architecture=_architecture(), clusters_by_id=clusters_by_id,
        topics_by_id=topics_by_id, keywords_by_id=keywords_by_id, base_url="https://site.com/")
    assert is_pillar is False
    urls = [t.url for t in targets]
    # up-link to the pillar (silo root) + lateral to c2
    assert "https://site.com/retatrutide-basics/" in urls
    assert "https://site.com/retatrutide-basics/retatrutide-side-effects" in urls
    up = next(t for t in targets if t.url.endswith("/retatrutide-basics/"))
    assert "retatrutide" in up.anchors
    peer = next(t for t in targets if t.url.endswith("retatrutide-side-effects"))
    assert "retatrutide side effects" in peer.anchors


def test_build_targets_empty_for_non_supporting_cluster():
    from app.writer.link_targets import build_targets

    targets, is_pillar = build_targets(
        "unknown", architecture=_architecture(), clusters_by_id={}, topics_by_id={},
        keywords_by_id={}, base_url="https://site.com")
    assert targets == [] and is_pillar is False


def test_build_targets_skips_peer_without_slug():
    from app.writer.link_targets import build_targets

    clusters_by_id = {  # c2 has no slug yet -> the lateral link is skipped
        "c1": {"id": "c1", "topic_id": "t1", "name": "A", "primary_keyword_id": "k1", "slug": "a"},
        "c2": {"id": "c2", "topic_id": "t1", "name": "B", "primary_keyword_id": "k2", "slug": None},
    }
    targets, _ = build_targets(
        "c1", architecture=_architecture(), clusters_by_id=clusters_by_id,
        topics_by_id={"t1": {"id": "t1", "name": "Silo"}}, keywords_by_id={}, base_url="https://s.com")
    assert all("/silo/b" not in t.url for t in targets)     # peer without slug dropped
    assert any(t.url == "https://s.com/silo/" for t in targets)   # up-link still present
