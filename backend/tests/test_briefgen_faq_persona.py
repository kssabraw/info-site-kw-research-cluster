"""M13 slice 5c-i — FAQ pure cores (Steps 10/10.5) + persona (Step 6, injected LLM)."""

from app.briefgen.faq import (
    FaqCandidate,
    ScoredFaq,
    build_intent_profile,
    extract_questions,
    score_faq,
    select_faqs,
    source_signal,
)
from app.briefgen.persona import Persona, generate_persona


# ----- FAQ pure cores -------------------------------------------------------

def test_extract_questions_word_count_filter():
    texts = [
        "Is retatrutide safe for long term use?",          # 7 words -> keep
        "Why?",                                             # too short -> drop
        "This is a statement without a question mark.",     # no ? -> drop
        "what is the absolute maximum dose anyone has ever safely taken weekly without side effects at all ever",  # >25 -> drop
    ]
    qs = extract_questions(texts)
    assert qs == ["Is retatrutide safe for long term use?"]


def test_source_signal_branches():
    assert source_signal("paa") == 1.0
    assert source_signal("reddit", 60) == 0.9
    assert source_signal("reddit", 20) == 0.6
    assert source_signal("reddit", 2) == 0.3
    assert source_signal("llm_concern") == 0.5
    assert source_signal("persona_gap") == 0.6


def test_build_intent_profile_and_score():
    assert build_intent_profile("informational", "T", "scope", "goal") == "informational T scope goal"
    assert build_intent_profile("informational", "T", "", "") == "informational T"
    assert round(score_faq(1.0, 0.5, 1.0), 3) == 0.8   # .4 + .2 + .2


def _sf(q, score, role="matches_primary_intent"):
    return ScoredFaq(FaqCandidate(q, "paa"), score, role)


def test_select_faqs_threshold_and_cap():
    scored = [_sf(f"q{i}", s) for i, s in enumerate([0.9, 0.8, 0.7, 0.6, 0.55, 0.4])]
    sel = select_faqs(scored)
    assert [s.candidate.question for s in sel] == ["q0", "q1", "q2", "q3", "q4"]   # top 5 >=0.5


def test_select_faqs_relaxation_when_few_pass():
    # only 1 primary passes 0.5; top up to 3 with adjacent, ignoring the threshold.
    scored = [
        _sf("p1", 0.7), _sf("p2", 0.3),
        _sf("a1", 0.45, "adjacent_intent"), _sf("a2", 0.4, "adjacent_intent"),
        _sf("d1", 0.9, "different_audience"),   # never selected (caller drops these)
    ]
    sel = [s.candidate.question for s in select_faqs(scored)]
    assert sel == ["p1", "p2", "a1"]            # top 3: primary by score then adjacent
    assert "d1" not in sel


def test_select_faqs_honest_shortfall():
    assert len(select_faqs([_sf("only", 0.2)])) == 1   # fewer than lo available -> return all


# ----- persona (injected LLM) ----------------------------------------------

class _LLM:
    def __init__(self, payload):
        self.payload = payload

    def call_tool(self, **kw):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_generate_persona_parses():
    llm = _LLM({
        "persona": {"description": "a curious patient", "background_assumptions": ["new to glp drugs"],
                    "primary_goal": "understand if it's right for them"},
        "gap_questions": [{"question": "is it covered by insurance?", "rationale": "cost"}, {"question": ""}],
    })
    p = generate_persona("retatrutide", intent_type="informational", title="T", scope_statement="s",
                         serp_h1s=[], serp_metas=[], candidate_headings=[], llm=llm)
    assert p.primary_goal == "understand if it's right for them"
    assert len(p.gap_questions) == 1 and p.gap_questions[0]["question"] == "is it covered by insurance?"


def test_generate_persona_degrades_to_empty_on_failure():
    p = generate_persona("k", intent_type="informational", title="T", scope_statement="s",
                         serp_h1s=[], serp_metas=[], candidate_headings=[],
                         llm=_LLM(RuntimeError("boom")))
    assert isinstance(p, Persona) and p.primary_goal == "" and p.gap_questions == []
