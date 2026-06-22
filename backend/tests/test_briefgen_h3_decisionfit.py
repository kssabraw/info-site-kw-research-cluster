"""M13 slice 5c-iii/iv — H3 selection + decision-fit pure cores."""

from app.briefgen.decision_fit import build_decision_fit_directive, detect_partner_factor
from app.briefgen.h3 import merge_h3s, mmr_select, parent_relevance_filter


# ----- H3 pure cores --------------------------------------------------------

def test_parent_relevance_band_filters_and_sorts():
    pairs = [("too low", 0.5), ("good a", 0.7), ("restatement", 0.9), ("good b", 0.8)]
    assert parent_relevance_filter(pairs) == [("good b", 0.8), ("good a", 0.7)]


def test_mmr_select_drops_redundant():
    # a and a2 are near-identical (cosine 1); MMR keeps the higher-ranked, drops the dup.
    ranked = [("a", 0.84), ("a2", 0.83), ("b", 0.7)]
    vecs = {"a": [1, 0], "a2": [1, 0], "b": [0, 1]}
    assert mmr_select(ranked, vecs, k=2, redundancy=0.78) == ["a", "b"]


def test_merge_h3s_authority_priority_and_overflow():
    regular = {"H2": [{"text": "r1"}, {"text": "r2"}]}
    authority = {"H2": [{"text": "a1"}, {"text": "a2"}]}     # 2 authority -> displaces both regular
    merged = merge_h3s(regular, authority, cap=2)
    assert [h["text"] for h in merged["H2"]] == ["a1", "a2"]
    # one authority + cap room for one regular
    merged2 = merge_h3s({"H2": [{"text": "r1"}, {"text": "r2"}]}, {"H2": [{"text": "a1"}]}, cap=2)
    assert [h["text"] for h in merged2["H2"]] == ["r1", "a1"]
    # 3 authority on a 2-cap H2 -> kept (overflow to cap+1, never discard authority)
    merged3 = merge_h3s({}, {"H2": [{"text": "a1"}, {"text": "a2"}, {"text": "a3"}]}, cap=2)
    assert [h["text"] for h in merged3["H2"]] == ["a1", "a2", "a3"]


# ----- decision-fit ---------------------------------------------------------

def test_detect_partner_factor():
    assert detect_partner_factor("comparison", []) == "comparative_depth"
    assert detect_partner_factor("how-to", [{"text": "X vs Y", "source": "mcs"}]) == "comparative_depth"
    assert detect_partner_factor("how-to", [{"text": "edge", "source": "authority_gap_sme"}]) == "edge_case_detail"
    assert detect_partner_factor("informational", [{"text": "h", "source": "mcs"}]) == "direct_definitions"
    assert detect_partner_factor("how-to", [{"text": "do this", "source": "mcs"}]) is None


class _LLM:
    def __init__(self, payload):
        self.payload = payload

    def call_tool(self, **kw):
        return self.payload


def test_build_decision_fit_directive_emits_when_gated():
    detection = {"confidence": 0.9, "rationale": "depends on reader",
                 "candidate_conditions": [{"condition": "beginner"}, {"condition": "advanced"}]}
    llm = _LLM({"branches": [
        {"condition": "If you're a beginner", "option": "start low", "source": "paa"},
        {"condition": "If you're advanced", "option": "titrate up", "source": "reddit"},
    ], "default_statement": "Most readers should start conservatively."})
    d = build_decision_fit_directive(detection, anchor_h2_text="Which dose?", persona_gaps=[],
                                     paa=[], reddit=[], partner_factor="comparative_depth", llm=llm)
    assert d["type"] == "decision_fit" and d["partner_factor"] == "comparative_depth"
    assert len(d["branches"]) == 2 and d["anchor_h2_text"] == "Which dose?"
    assert d["constraints"]["min_branches"] == 2


def test_build_decision_fit_directive_none_without_partner():
    assert build_decision_fit_directive({"candidate_conditions": []}, anchor_h2_text="x",
                                        persona_gaps=[], paa=[], reddit=[], partner_factor=None,
                                        llm=_LLM({})) is None


def test_build_decision_fit_directive_none_with_one_branch():
    llm = _LLM({"branches": [{"condition": "only one", "option": "x"}], "default_statement": "d"})
    assert build_decision_fit_directive({"candidate_conditions": []}, anchor_h2_text="x",
                                        persona_gaps=[], paa=[], reddit=[],
                                        partner_factor="direct_definitions", llm=llm) is None
