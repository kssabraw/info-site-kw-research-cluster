"""M13 Brief Generator — Brief Output model tests (foundation slice).

Validates the v2.6 contract: load-bearing Writer fields parse, defaults are sane,
and `extra="allow"` lets production scoring metadata + the future answer-engine
fields (aio_target / MCS scores) ride along without hard-failing.

Guarded so the pure-test sandbox (no pydantic) skips; runs in CI/deploy."""


def _models():
    try:
        import pydantic  # noqa: F401

        from app.briefgen import models
    except ImportError:
        return None
    return models


def test_brief_output_roundtrips_v26_contract():
    m = _models()
    if m is None:
        return  # no pydantic — covered in CI/deploy
    # A trimmed but representative v2.6 brief_output (live-contract keys).
    raw = {
        "schema_version": "2.6",
        "keyword": "is retatrutide a glp-3 drug",
        "h1": "Is Retatrutide a GLP-3 Drug?",
        "title": "Is Retatrutide a GLP-3 Drug? What the Science Says",
        "title_rationale": "leads with the entity + the question intent",
        "scope_statement": "Covers mechanism and class; does not cover dosing.",
        "intent_type": "informational",
        "intent_confidence": 0.82,
        "intent_review_required": False,
        "format_directives": {
            "require_tables": True, "min_tables_per_article": 1,
            "min_lists_per_article": 2, "require_bulleted_lists": True,
            "min_h2_body_words": 180, "answer_first_paragraphs": True,
            "preferred_paragraph_max_words": 80,
        },
        "heading_structure": [
            {"text": "Is Retatrutide a GLP-3 Drug?", "level": "H1", "order": 1,
             "type": "content", "source": "serp", "serp_frequency": 7},
            {"text": "How retatrutide works", "level": "H2", "order": 2,
             "type": "content"},
            {"text": "GLP-1 vs GIP vs glucagon", "level": "H3", "order": 3,
             "parent_h2_text": "How retatrutide works"},
        ],
        "faqs": [{"question": "Is retatrutide FDA approved?", "answer": "Not yet."}],
        "metadata": {"brief_schema_version": "2.6"},
    }
    b = m.BriefOutput(**raw)
    assert b.keyword == "is retatrutide a glp-3 drug"
    assert b.title.startswith("Is Retatrutide")
    assert b.format_directives.min_h2_body_words == 180
    assert b.format_directives.require_tables is True
    # load-bearing heading fields
    h3 = b.heading_structure[2]
    assert h3.level == "H3" and h3.parent_h2_text == "How retatrutide works"
    # SERP scoring metadata preserved where present, null elsewhere
    assert b.heading_structure[0].serp_frequency == 7
    assert b.heading_structure[1].serp_frequency is None
    assert b.faqs[0].question.startswith("Is retatrutide")


def test_defaults_and_extra_fields_allowed():
    m = _models()
    if m is None:
        return
    # Minimal brief: only keyword required; everything else defaults.
    b = m.BriefOutput(keyword="kw")
    assert b.schema_version == m.SCHEMA_VERSION == "2.6"
    assert b.heading_structure == [] and b.faqs == []
    assert b.format_directives.require_tables is False
    assert b.intent_review_required is False
    # Answer-engine-first additions (added by later slices) must not hard-fail.
    b2 = m.BriefOutput(
        keyword="kw",
        aio_target={"present": True, "answer_text": "…", "cited_sources": []},
        heading_structure=[{"text": "h", "level": "H2", "order": 1, "mcs_score": 0.71}],
    )
    assert b2.aio_target["present"] is True            # extra top-level field kept
    assert b2.heading_structure[0].mcs_score == 0.71   # extra heading field kept
