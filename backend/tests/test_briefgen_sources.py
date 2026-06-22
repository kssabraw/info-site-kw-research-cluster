"""M13 slice 2 — pure parser tests for Brief Gen source gathering (no egress)."""

from app.briefgen.sources import (
    parse_aio,
    parse_llm_answer,
    parse_organic,
    parse_paa,
    parse_reddit,
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


def test_parse_reddit_only_reddit_urls():
    items = [
        {"type": "organic", "url": "https://www.reddit.com/r/x/abc", "title": "T", "description": "d"},
        {"type": "organic", "url": "https://notreddit.com/y", "title": "N"},
        {"type": "ai_overview"},
    ]
    out = parse_reddit(items)
    assert len(out) == 1 and out[0]["url"].endswith("/abc") and out[0]["title"] == "T"


def test_parse_llm_answer_pulls_text_from_common_shapes():
    # flat text
    assert parse_llm_answer([{"type": "llm_responses", "text": "answer one"}]) == "answer one"
    # nested sections
    nested = [{"type": "llm_responses", "sections": [{"text": "part a"}, {"text": "part b"}, {}]}]
    assert parse_llm_answer(nested) == "part a\npart b"
    # nothing usable -> None
    assert parse_llm_answer([{"type": "x"}, "junk"]) is None
