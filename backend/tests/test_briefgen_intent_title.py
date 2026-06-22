"""M13 slice 5a — intent (Step 3 + A1) + title (Step 3.5) pure tests + injected-LLM."""

import pytest

from app.briefgen.intent import (
    classify_intent,
    decision_fit_qualifies,
    format_directives_for,
    get_intent_template,
)
from app.briefgen.title import (
    TitleGenerationError,
    generate_title_scope,
    validate_title_scope,
)


# ----- intent template registry --------------------------------------------

def test_get_intent_template_aliases_and_fallback():
    assert get_intent_template("how-to")["h2_pattern"] == "sequential_steps"
    assert get_intent_template("guide")["intent"] == "informational"        # alias
    assert get_intent_template("review")["intent"] == "informational-commercial"
    fb = get_intent_template("totally-unknown")                              # fallback
    assert fb["intent"] == "informational" and fb["h2_pattern"] == "topic_questions"


def test_format_directives_per_pattern_floor():
    assert format_directives_for(get_intent_template("how-to"))["min_h2_body_words"] == 150
    assert format_directives_for(get_intent_template("listicle"))["min_h2_body_words"] == 140
    assert format_directives_for(get_intent_template("informational"))["min_h2_body_words"] == 180
    fd = format_directives_for(get_intent_template("comparison"))
    assert fd["require_tables"] is True and fd["min_lists_per_article"] == 2


# ----- A1 decision-fit gate -------------------------------------------------

def test_decision_fit_gate():
    ok = {"is_multi_answer": True, "confidence": 0.8,
          "candidate_conditions": [{"condition": "beginner"}, {"condition": "advanced"}]}
    assert decision_fit_qualifies(ok) is True
    assert decision_fit_qualifies({**ok, "is_multi_answer": False}) is False     # not multi
    assert decision_fit_qualifies({**ok, "confidence": 0.5}) is False             # below tau
    one = {**ok, "candidate_conditions": [{"condition": "beginner"}, {"condition": "Beginner"}]}
    assert decision_fit_qualifies(one) is False                                   # dedups to 1


# ----- classify_intent (injected LLM) --------------------------------------

class _IntentLLM:
    def __init__(self, payload):
        self.payload = payload

    def call_tool(self, **kw):
        return self.payload


def test_classify_intent_review_flag_and_decision_fit_wiring():
    llm = _IntentLLM({
        "intent_type": "how-to", "intent_confidence": 0.6,
        "decision_fit_detection": {"is_multi_answer": True, "confidence": 0.9,
                                   "candidate_conditions": [{"condition": "a"}, {"condition": "b"}]},
    })
    r = classify_intent("how to x", serp_titles=[], serp_h2s=[], paa=[], llm=llm)
    assert r.intent_type == "how-to"
    assert r.intent_review_required is True               # conf 0.6 < 0.75, precheck didn't fire
    assert r.intent_format_template["h2_pattern"] == "sequential_steps"
    assert r.decision_fit_qualifies is True
    # high confidence + precheck fired -> no review
    llm2 = _IntentLLM({"intent_type": "guide", "intent_confidence": 0.62,
                       "decision_fit_detection": {"is_multi_answer": False, "confidence": 0.1}})
    r2 = classify_intent("what is x", serp_titles=[], serp_h2s=[], paa=[], llm=llm2,
                         keyword_precheck_fired=True)
    assert r2.intent_type == "informational"              # alias collapsed
    assert r2.intent_review_required is False and r2.decision_fit_qualifies is False


# ----- title + scope --------------------------------------------------------

def test_validate_title_scope():
    assert validate_title_scope({"title": "Good Title", "scope_statement": "Covers x. Does not cover y."}) is None
    assert validate_title_scope({"title": "", "scope_statement": "Does not cover y"}) == "title_empty_or_too_long"
    assert validate_title_scope({"title": "x" * 101, "scope_statement": "Does not cover y"}) == "title_empty_or_too_long"
    assert validate_title_scope({"title": "T", "scope_statement": "no clause here"}) == "scope_missing_does_not_cover"


class _TitleLLM:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = 0

    def call_tool(self, **kw):
        self.calls += 1
        return self.payloads.pop(0)


def test_generate_title_scope_retries_then_succeeds():
    llm = _TitleLLM(
        {"title": "", "scope_statement": "bad"},                                   # invalid -> retry
        {"title": "What Retatrutide Is", "scope_statement": "Defines it. Does not cover dosing."},
    )
    ts = generate_title_scope("retatrutide", intent_type="informational", serp_titles=[],
                              serp_h1s=[], serp_metas=[], llm_answers={}, llm=llm)
    assert ts.title == "What Retatrutide Is" and llm.calls == 2


def test_generate_title_scope_aborts_after_retries():
    llm = _TitleLLM({"title": "", "scope_statement": "x"}, {"title": "", "scope_statement": "y"})
    with pytest.raises(TitleGenerationError):
        generate_title_scope("k", intent_type="informational", serp_titles=[], serp_h1s=[],
                             serp_metas=[], llm_answers={}, llm=llm)
