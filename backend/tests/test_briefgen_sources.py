"""M13 slice 2 — pure parser tests for Brief Gen source gathering (no egress)."""

from app.briefgen.sources import (
    parse_aio,
    parse_discussions_forums,
    parse_llm_answer,
    parse_organic,
    parse_paa,
)


def test_parse_organic_keeps_metadata_and_skips_non_organic():
    items = [
        {"type": "ai_overview"},
        {"type": "organic", "url": "https://a.com/x", "title": "A", "description": "da", "rank_absolute": 1},
        {"type": "people_also_ask", "items": [{"title": "q?"}]},
        {"type": "organic", "url": "https://b.com/y", "title": "B", "rank_absolute": 3},
        {"type": "organic"},  # no url -> dropped
    ]
    out = parse_organic(items, depth=20)
    assert [o["url"] for o in out] == ["https://a.com/x", "https://b.com/y"]
    assert out[0]["rank"] == 1 and out[0]["description"] == "da"
    assert out[1]["rank"] == 3


def test_parse_paa_collects_questions():
    items = [{"type": "people_also_ask", "items": [{"title": "is x y?"}, {"title": "how z?"}, {}]}]
    assert parse_paa(items) == ["is x y?", "how z?"]


def test_parse_aio_present_with_text_and_sources():
    items = [
        {"type": "organic", "url": "https://a.com"},
        {"type": "ai_overview",
         "text": "Retatrutide is a triple agonist.",
         "items": [{"text": "It targets GLP-1, GIP, and glucagon."}, {"foo": "bar"}],
         "references": [
             {"url": "https://nih.gov/x", "domain": "nih.gov", "title": "NIH"},
             {"domain": "nourl.com"},  # no url -> skipped
         ]},
    ]
    aio = parse_aio(items)
    assert aio["present"] is True
    assert "triple agonist" in aio["answer_text"] and "GLP-1" in aio["answer_text"]
    assert aio["cited_sources"] == [{"url": "https://nih.gov/x", "domain": "nih.gov", "title": "NIH"}]


def test_parse_aio_absent_is_normal():
    aio = parse_aio([{"type": "organic", "url": "https://a.com"}])
    assert aio == {"present": False, "answer_text": "", "cited_sources": []}


def test_parse_discussions_forums_container_and_flat():
    items = [
        {"type": "organic", "url": "https://a.com"},
        {"type": "discussions_and_forums", "items": [
            {"type": "discussions_and_forums_element",
             "title": "Anyone tried retatrutide?", "url": "https://www.reddit.com/r/x/1",
             "domain": "reddit.com", "posts_count": 42},
            {"title": "no url here"},  # dropped
        ]},
        # also accept a flat element at the top level
        {"type": "discussions_and_forums_element", "title": "Quora q",
         "url": "https://www.quora.com/q", "domain": "quora.com"},
    ]
    out = parse_discussions_forums(items)
    assert [t["url"] for t in out] == ["https://www.reddit.com/r/x/1", "https://www.quora.com/q"]
    assert out[0]["posts_count"] == 42 and out[0]["domain"] == "reddit.com"
    assert out[1]["posts_count"] is None


def test_parse_llm_answer_pulls_text_from_common_shapes():
    # flat text
    assert parse_llm_answer([{"type": "llm_responses", "text": "answer one"}]) == "answer one"
    # nested sections
    nested = [{"type": "llm_responses", "sections": [{"text": "part a"}, {"text": "part b"}, {}]}]
    assert parse_llm_answer(nested) == "part a\npart b"
    # nothing usable -> None
    assert parse_llm_answer([{"type": "x"}, "junk"]) is None
    # a non-list `sections` must not crash, and the sibling text still survives
    assert parse_llm_answer([{"text": "good", "sections": {"x": "y"}}]) == "good"
