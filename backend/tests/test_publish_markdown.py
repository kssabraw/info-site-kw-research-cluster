"""Astro-content Markdown builder (pure)."""

from datetime import date

from app.writer.publish.markdown import (
    _derive_description,
    _split_title,
    build_astro_markdown,
)


def test_split_title_lifts_leading_h1():
    title, body = _split_title("# Retatrutide Structure\n\nIt is a peptide.")
    assert title == "Retatrutide Structure"
    assert body == "It is a peptide."


def test_split_title_none_when_no_leading_h1():
    title, body = _split_title("Intro paragraph.\n\n## Section")
    assert title is None and body.startswith("Intro paragraph.")


def test_derive_description_skips_headings_and_trims():
    body = "## Heading\n\n- bullet\n\nRetatrutide is a triple agonist peptide under study."
    assert _derive_description(body) == "Retatrutide is a triple agonist peptide under study."
    long = "word " * 60
    assert _derive_description(long).endswith("…")


def test_build_astro_markdown_frontmatter_and_body():
    md = build_astro_markdown(
        article_markdown="# Retatrutide Dosing\n\nStart low and titrate up over weeks.",
        title="", slug="retatrutide-dosing", silo="Retatrutide Basics",
        pub_date=date(2026, 6, 23),
    )
    assert md.startswith("---\n")
    assert 'title: "Retatrutide Dosing"' in md          # lifted from the H1
    assert 'slug: "retatrutide-dosing"' in md
    assert 'silo: "Retatrutide Basics"' in md
    assert "pubDate: 2026-06-23" in md
    assert "draft: false" in md
    # the H1 is not duplicated in the body
    assert md.count("# Retatrutide Dosing") == 0
    assert "Start low and titrate up over weeks." in md


def test_build_astro_markdown_escapes_quotes_and_takes_explicit_title():
    md = build_astro_markdown(
        article_markdown="Body only, no h1.", title='The "Best" Guide',
        slug="best-guide", silo="Silo", description="A guide.",
    )
    assert 'title: "The \\"Best\\" Guide"' in md
    assert 'description: "A guide."' in md
