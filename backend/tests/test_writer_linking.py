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
