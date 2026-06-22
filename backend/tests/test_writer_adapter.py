"""M14 slice 2 — Writer adapter (field-mapper + Step 0 cross-validation)."""

import pytest

from app.writer.adapter import (
    adapt_brief,
    adapt_sie,
    build_writer_inputs,
    cross_validate,
    degraded_sie,
)
from app.writer.models import WriterAbort


def _brief_json(faq_count=3, headings=None):
    if headings is None:
        headings = [
            {"order": 1, "level": "H1", "text": "Is Retatrutide a GLP-3 Drug?", "type": "content"},
            {"order": 2, "level": "H2", "text": "Retatrutide is a triple agonist", "type": "content"},
            {"order": 3, "level": "H3", "text": "How GLP-1 differs from GIP", "type": "content",
             "parent_h2_text": "Retatrutide is a triple agonist"},
        ]
    return {
        "keyword": "is retatrutide a glp-3 drug",
        "title": "Is Retatrutide a GLP-3 Drug? Explained",
        "intent_type": "informational",
        "scope_statement": "Explains it. Does not cover dosing.",
        "heading_structure": headings,
        "faqs": [{"question": f"Q{i}?", "faq_score": 0.9 - i * 0.1} for i in range(faq_count)],
        "format_directives": {"require_tables": True, "min_h2_body_words": 150},
        "metadata": {},
    }


def _sie_json():
    return {
        "schema_version": "1.4", "keyword": "is retatrutide a glp-3 drug",
        "word_count": {"target": 2500, "min": 2000, "max": 3000},
        "target_keyword": {"term": "is retatrutide a glp-3 drug",
                           "minimum_usage": {"h2": 1, "h3": 0, "paragraphs": 6}},
        "terms": {"required": [{"term": "glp-1", "recommendation_score": 0.9, "is_entity": True,
                                "entity_category": "Drug Class"}], "avoid": []},
        "usage_recommendations": [], "entities": [],
    }


def test_adapt_brief_appends_faq_and_conclusion_and_renumbers():
    b = adapt_brief(_brief_json(faq_count=3))
    types = [(h.level, h.type, h.text) for h in b.heading_structure]
    # original 3 content rows, then faq-header, 3 faq-question, then conclusion
    assert types[0][1] == "content" and types[3] == ("H2", "faq-header", "Frequently Asked Questions")
    assert [t[1] for t in types[4:7]] == ["faq-question", "faq-question", "faq-question"]
    assert types[-1] == ("H2", "conclusion", "Conclusion")
    assert [h.order for h in b.heading_structure] == list(range(1, len(b.heading_structure) + 1))
    # metadata counts (content only): 1 H2 + 1 H3
    assert b.metadata["h2_count"] == 1 and b.metadata["h3_count"] == 1
    assert b.metadata["word_budget"] == 2500
    # format_directives default fills max_sentences_per_paragraph
    assert b.format_directives.require_tables is True
    assert b.format_directives.max_sentences_per_paragraph == 4


def test_adapt_sie_parses_native_shape():
    sie = adapt_sie(_sie_json(), keyword="is retatrutide a glp-3 drug", word_budget=2500)
    assert sie.terms.required[0].is_entity is True
    assert sie.word_count.target == 2500


def test_degraded_sie_flat_defaults():
    sie = degraded_sie("k", word_budget=2000, supporting_keywords=["glp-1", "tirzepatide", "glp-1"])
    assert [r.term for r in sie.terms.required] == ["glp-1", "tirzepatide"]   # deduped
    assert sie.usage_recommendations[0].paragraphs.target == 1
    assert sie.usage_recommendations[0].paragraphs.max == 3
    assert sie.word_count.target == 2000 and sie.word_count.max == 2400
    assert sie.entities == [] and sie.warnings


def test_adapt_sie_falls_back_when_absent():
    sie = adapt_sie(None, keyword="k", word_budget=2500, supporting_keywords=["a", "b"])
    assert len(sie.terms.required) == 2 and sie.warnings


def test_cross_validate_ok_sets_no_citations():
    brief = adapt_brief(_brief_json(faq_count=4))
    sie = adapt_sie(_sie_json(), keyword="is retatrutide a glp-3 drug", word_budget=2500)
    w = cross_validate(brief, sie)
    assert w["no_citations"] is True and w["word_count_conflict"] is False


def test_cross_validate_word_count_conflict():
    brief = adapt_brief(_brief_json(faq_count=3))
    sie = adapt_sie(None, keyword="is retatrutide a glp-3 drug", word_budget=2500)
    # force a divergent SIE target (>20%)
    sie.word_count.target = 1000
    assert cross_validate(brief, sie)["word_count_conflict"] is True


def test_cross_validate_aborts_on_faq_out_of_band():
    brief = adapt_brief(_brief_json(faq_count=2))
    sie = adapt_sie(_sie_json(), keyword="is retatrutide a glp-3 drug", word_budget=2500)
    with pytest.raises(WriterAbort) as ei:
        cross_validate(brief, sie)
    assert ei.value.code == "faq_count_invalid"


def test_cross_validate_aborts_on_keyword_mismatch():
    brief = adapt_brief(_brief_json(faq_count=3))
    sie = adapt_sie({**_sie_json(), "keyword": "something else"},
                    keyword="something else", word_budget=2500)
    with pytest.raises(WriterAbort) as ei:
        cross_validate(brief, sie)
    assert ei.value.code == "keyword_mismatch"


def test_cross_validate_aborts_on_empty_headings():
    brief = adapt_brief(_brief_json(faq_count=3, headings=[]))
    sie = adapt_sie(_sie_json(), keyword="is retatrutide a glp-3 drug", word_budget=2500)
    with pytest.raises(WriterAbort) as ei:
        cross_validate(brief, sie)
    assert ei.value.code == "empty_heading_structure"


def test_build_writer_inputs_clamps_faqs_over_five():
    brief, sie, warnings = build_writer_inputs(
        _brief_json(faq_count=7), _sie_json(),
    )
    assert len(brief.faqs) == 5
    # appended faq-question rows match the kept FAQs
    fq = [h.text for h in brief.heading_structure if h.type == "faq-question"]
    assert len(fq) == 5
    assert [h.order for h in brief.heading_structure] == list(range(1, len(brief.heading_structure) + 1))
    assert warnings["no_citations"] is True


def test_adapt_brief_preserves_format_directive():
    bj = _brief_json(faq_count=3)
    bj["heading_structure"][1]["format_directive"] = {
        "type": "decision_fit",
        "branches": [{"condition": "a", "option": "x"}, {"condition": "b", "option": "y"}],
        "default_statement": "d"}
    b = adapt_brief(bj)
    anchor = next(h for h in b.heading_structure if h.text == "Retatrutide is a triple agonist")
    assert anchor.format_directive["type"] == "decision_fit"
    assert len(anchor.format_directive["branches"]) == 2
