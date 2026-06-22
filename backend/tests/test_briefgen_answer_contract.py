"""M13 enhancement — answer contract: parsing, scope gate, lead prepend."""

from app.briefgen.answer_contract import (
    AnswerContract,
    build_scope_gate,
    generate_answer_contract,
)
from app.briefgen.mcs import MCSResult, ScoredHeading
from app.briefgen.pipeline import _prepend_answer_lead


class _LLM:
    def __init__(self, payload):
        self.payload = payload

    def call_tool(self, **kw):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_generate_answer_contract_parses():
    llm = _LLM({
        "explicit_question": "Is retatrutide a GLP-3 drug?",
        "implied_need": "what retatrutide actually is",
        "direct_answer": "No. There is no GLP-3 drug class; retatrutide is a GLP-1/GIP/glucagon triple agonist.",
        "answer_heading": "No, retatrutide is not a GLP-3 drug",
        "must_cover": ["triple-agonist mechanism", "what GLP-3 means", "GLP-1 vs GIP vs glucagon"],
        "must_not_cover": ["dosing", "FDA approval status", "clinical trial access"],
    })
    c = generate_answer_contract(
        "is retatrutide a glp-3 drug", title="t", scope_statement="s",
        intent_type="informational", aio_answer="a", chatgpt_answer="b", llm=llm)
    assert c.answer_heading == "No, retatrutide is not a GLP-3 drug"
    assert "FDA approval status" in c.must_not_cover
    assert c.as_metadata()["explicit_question"].startswith("Is retatrutide")


def test_generate_answer_contract_degrades_on_failure():
    c = generate_answer_contract(
        "k", title="t", scope_statement="s", intent_type="x",
        aio_answer="", chatgpt_answer="", llm=_LLM(RuntimeError("boom")))
    assert c == AnswerContract()  # empty -> MCS runs unguided


def test_build_scope_gate_drops_off_scope():
    # 1-D embeddings: cover ~ +1 axis, avoid ~ -1 axis. Candidates near avoid are dropped.
    def embed(texts):
        table = {
            "mechanism": [1.0, 0.0], "receptors": [0.9, 0.1],
            "fda approval": [0.0, 1.0], "trial access": [0.05, 1.0],
            "good cand": [0.95, 0.05], "off-scope cand": [0.0, 1.0],
        }
        return [table.get(t, [0.5, 0.5]) for t in texts]

    contract = AnswerContract(must_cover=["mechanism", "receptors"],
                              must_not_cover=["fda approval", "trial access"])
    gate = build_scope_gate(contract, embed)
    kept = gate(["good cand", "off-scope cand"])
    assert kept == ["good cand"]


def test_build_scope_gate_noop_without_exclusions():
    gate = build_scope_gate(AnswerContract(must_cover=["x"]), lambda t: [[1.0] for _ in t])
    assert gate(["a", "b"]) == ["a", "b"]


def _sh(text):
    return ScoredHeading(text=text, point_cosines=[], chatgpt_cosine=0.0, aio_headline=0.0, blended=0.5)


def test_prepend_answer_lead_leads_and_dedups():
    mcs = MCSResult(selected=[
        _sh("Retatrutide is not a GLP-3 drug after all"),     # contains the lead -> dropped
        _sh("Retatrutide targets three receptors"),
        _sh("Retatrutide drives weight loss"),
    ])
    contract = AnswerContract(answer_heading="Retatrutide is not a GLP-3 drug")
    _prepend_answer_lead(mcs, contract, max_count=12)
    texts = [s.text for s in mcs.selected]
    assert texts[0] == "Retatrutide is not a GLP-3 drug"
    assert "Retatrutide targets three receptors" in texts
    assert len(texts) == 3   # lead + 2 distinct (the containment restatement dropped)


def test_prepend_answer_lead_trims_to_max():
    mcs = MCSResult(selected=[_sh(f"H{i}") for i in range(12)])
    _prepend_answer_lead(mcs, AnswerContract(answer_heading="Lead H2"), max_count=12)
    assert len(mcs.selected) == 12 and mcs.selected[0].text == "Lead H2"


def test_prepend_answer_lead_noop_without_heading():
    mcs = MCSResult(selected=[_sh("a"), _sh("b")])
    _prepend_answer_lead(mcs, AnswerContract(answer_heading=""), max_count=12)
    assert [s.text for s in mcs.selected] == ["a", "b"]
