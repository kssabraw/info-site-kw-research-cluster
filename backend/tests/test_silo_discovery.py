import pytest

from app.dataforseo import DataForSEOError
from app.llm.openai_client import OpenAILLM
from app.pipeline.models import GroundingResult, ProposedSilo, RelationshipType
from app.pipeline.silo_discovery import run_silo_discovery


class FakeLLM:
    def __init__(self, grounding: GroundingResult, silos: list[ProposedSilo]):
        self._grounding = grounding
        self._silos = silos
        self.proposed = False

    def ground_subject(self, seed, disambiguation_hint):
        return self._grounding

    def propose_silos(self, **kwargs):
        self.proposed = True
        return self._silos


class FakeDFS:
    def __init__(self, demand=None, paths=None, fail_demand=False, fail_serp=False):
        self._demand = demand or ["a", "b"]
        self._paths = paths or ["dosing", "side-effects"]
        self._fail_demand = fail_demand
        self._fail_serp = fail_serp

    def keyword_ideas_sample(self, seed, limit=200):
        if self._fail_demand:
            raise DataForSEOError("boom")
        return self._demand

    def serp_competitor_paths(self, seed, top_n=5):
        if self._fail_serp:
            raise DataForSEOError("boom")
        return self._paths


def _silo(name, rel=RelationshipType.property_or_mechanism):
    return ProposedSilo(name=name, relationship_type=rel)


def test_normal_run_returns_silos():
    llm = FakeLLM(
        GroundingResult(summary="s", detected_audience="clinicians", is_ambiguous=False),
        [_silo("triple agonist")],
    )
    result = run_silo_discovery(
        seed="retatrutide",
        topic_count=5,
        audience_hint=None,
        disambiguation_hint=None,
        llm=llm,
        dfs=FakeDFS(),
    )
    assert result.needs_disambiguation is False
    assert [s.name for s in result.silos] == ["triple agonist"]
    assert result.detected_audience == "clinicians"
    assert result.degraded_notes == []


def test_audience_hint_overrides_detected():
    llm = FakeLLM(GroundingResult(detected_audience="x"), [_silo("a")])
    result = run_silo_discovery(
        seed="seed",
        topic_count=5,
        audience_hint="biohackers",
        disambiguation_hint=None,
        llm=llm,
        dfs=FakeDFS(),
    )
    assert result.detected_audience == "biohackers"


def test_disambiguation_gate_pauses_before_proposal():
    llm = FakeLLM(
        GroundingResult(is_ambiguous=True, interpretations=["planet", "element"]),
        [_silo("should-not-be-used")],
    )
    result = run_silo_discovery(
        seed="mercury",
        topic_count=5,
        audience_hint=None,
        disambiguation_hint=None,
        llm=llm,
        dfs=FakeDFS(),
    )
    assert result.needs_disambiguation is True
    assert result.interpretations == ["planet", "element"]
    assert result.silos == []
    assert llm.proposed is False  # proposal must not run before disambiguation


def test_disambiguation_hint_skips_gate():
    # The orchestrator gate fires only when ambiguous AND no hint. A supplied hint
    # must skip the pause and proceed to proposal even if grounding still reports
    # ambiguity.
    llm = FakeLLM(
        GroundingResult(is_ambiguous=True, interpretations=["planet", "element"]),
        [_silo("toxicology")],
    )
    result = run_silo_discovery(
        seed="mercury",
        topic_count=5,
        audience_hint=None,
        disambiguation_hint="the chemical element",
        llm=llm,
        dfs=FakeDFS(),
    )
    assert result.needs_disambiguation is False
    assert [s.name for s in result.silos] == ["toxicology"]
    assert llm.proposed is True


def test_degraded_when_demand_sample_fails():
    llm = FakeLLM(GroundingResult(summary="s"), [_silo("a")])
    result = run_silo_discovery(
        seed="seed",
        topic_count=5,
        audience_hint=None,
        disambiguation_hint=None,
        llm=llm,
        dfs=FakeDFS(fail_demand=True),
    )
    assert result.silos  # still produced
    assert any("Demand sample unavailable" in n for n in result.degraded_notes)


@pytest.mark.parametrize(
    "raw,expected_names",
    [
        # peer_entity filtered out; valid kept
        (
            [
                {"name": "triple agonist", "relationship_type": "property_or_mechanism"},
                {"name": "tirzepatide", "relationship_type": "peer_entity"},
            ],
            ["triple agonist"],
        ),
        # off-taxonomy relationship_type dropped
        (
            [
                {"name": "good", "relationship_type": "use_case"},
                {"name": "bad", "relationship_type": "made_up"},
            ],
            ["good"],
        ),
        # accepts {"silos": [...]} wrapper
        ({"silos": [{"name": "x", "relationship_type": "use_case"}]}, ["x"]),
    ],
)
def test_parse_silos_filters(raw, expected_names):
    silos = OpenAILLM._parse_silos(raw)
    assert [s.name for s in silos] == expected_names


def test_parse_silos_flags_broader_class():
    silos = OpenAILLM._parse_silos(
        [{"name": "incretin mimetics", "relationship_type": "broader_class"}]
    )
    assert silos[0].is_broader_class is True
