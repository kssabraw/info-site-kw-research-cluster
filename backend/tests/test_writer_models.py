"""M14 slice 1 — Writer foundation models."""

import pytest

from app.writer.models import (
    ACCEPTED_SCHEMA_VERSIONS,
    SCHEMA_VERSION_NO_CONTEXT,
    ArticleItem,
    Brief,
    BriefFormatDirectives,
    IntentType,
    SieInput,
    WriterAbort,
    WriterOutput,
)


def test_brief_parses_minimal_and_keeps_extras():
    b = Brief(
        keyword="is retatrutide a glp-3 drug",
        title="Is Retatrutide a GLP-3 Drug? Explained",
        intent_type="informational",
        scope_statement="Explains it. Does not cover dosing.",
        heading_structure=[
            {"order": 1, "level": "H1", "text": "Is Retatrutide a GLP-3 Drug?"},
            {"order": 2, "level": "H2", "text": "Retatrutide is a triple agonist",
             "source": "mcs", "mcs_aio_cosine": 0.87},  # extra field preserved
        ],
        faqs=[{"question": "Is it approved?", "faq_score": 0.9}],
        metadata={"word_budget": 2500},
    )
    assert b.intent_type is IntentType.informational
    assert b.heading_structure[1].text == "Retatrutide is a triple agonist"
    # extra="allow" keeps unmodeled fields on the heading
    assert b.heading_structure[1].model_extra["mcs_aio_cosine"] == 0.87
    # format_directives defaults match the PRD
    assert b.format_directives.answer_first_paragraphs is True
    assert b.format_directives.max_sentences_per_paragraph == 4
    assert b.format_directives.min_lists_per_article == 1


def test_intent_enum_values():
    assert IntentType("how-to") is IntentType.how_to
    assert IntentType("local-seo") is IntentType.local_seo
    assert {i.value for i in IntentType} == {
        "informational", "listicle", "how-to", "comparison",
        "ecom", "local-seo", "news", "informational-commercial",
    }


def test_format_directives_defaults():
    fd = BriefFormatDirectives()
    assert fd.require_tables is False and fd.min_tables_per_article == 1
    assert fd.min_h2_body_words == 0


def test_sie_input_is_native_sie_output():
    # Input C is the SIE Final Output Model (schema 1.4) reused verbatim.
    sie = SieInput(
        keyword="k",
        word_count={"target": 2500, "min": 2000, "max": 3000},
        target_keyword={"term": "k", "minimum_usage": {"h2": 1, "h3": 0, "paragraphs": 6}},
        terms={"required": [{"term": "glp-1", "recommendation_score": 0.9, "is_entity": True,
                             "entity_category": "Drug Class"}], "avoid": []},
    )
    assert sie.schema_version == "1.4"
    assert sie.terms.required[0].is_entity is True


def test_writer_output_and_article_item():
    out = WriterOutput(
        keyword="k", intent_type="informational", title="T",
        article=[ArticleItem(order=1, level="H1", type="title", heading="T")],
        client_context_summary={"schema_version_effective": SCHEMA_VERSION_NO_CONTEXT},
        metadata={"no_citations": True},
    )
    assert out.article[0].level == "H1"
    assert out.client_context_summary["schema_version_effective"] in ACCEPTED_SCHEMA_VERSIONS
    assert out.metadata["no_citations"] is True


def test_writer_abort_carries_code():
    with pytest.raises(WriterAbort) as ei:
        raise WriterAbort("brief_missing_title", "no title")
    assert ei.value.code == "brief_missing_title"
    assert "brief_missing_title" in str(ei.value)
