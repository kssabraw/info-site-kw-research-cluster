"""M13 slice 5b — assemble (Step 11) unit test + generate_brief wiring smoke test."""

import hashlib
import math

from app.briefgen.assemble import build_brief_output
from app.briefgen.entity import MainEntity
from app.briefgen.intent import IntentResult, format_directives_for, get_intent_template
from app.briefgen.mcs import MCSResult, ScoredHeading
from app.briefgen.pipeline import BriefDeps, generate_brief
from app.briefgen.sources import BriefSources
from app.briefgen.title import TitleScope


def _intent(intent_type="informational", conf=0.9):
    tpl = get_intent_template(intent_type)
    return IntentResult(
        intent_type=tpl["intent"], intent_confidence=conf, intent_review_required=False,
        intent_format_template=tpl, format_directives=format_directives_for(tpl),
        decision_fit_detection={}, decision_fit_qualifies=False,
    )


def test_build_brief_output_assembles_v26():
    intent = _intent("how-to", 0.88)
    title = TitleScope(title="How Retatrutide Works", scope_statement="Explains it. Does not cover dosing.",
                       title_rationale="def framing")
    entity = MainEntity(canonical="retatrutide", variants=["reta"], source="aio", confidence=3.0)
    mcs = MCSResult(
        selected=[
            ScoredHeading("Retatrutide activates GLP-1", [0.9], 0.8, 0.9, 0.85),
            ScoredHeading("Retatrutide hits three receptors", [0.8], 0.7, 0.8, 0.75),
        ],
        pool=["a", "b", "c", "d"],
        discarded=[ScoredHeading("Retatrutide is a drug", [0.5], 0.5, 0.5, 0.5)],
    )
    sources = BriefSources(keyword="retatrutide", organic=[{}], paa=["q"],
                           llm_answers={"chat_gpt": "answer", "gemini": "answer2"})

    b = build_brief_output(keyword="retatrutide", intent=intent, title=title, entity=entity,
                           mcs=mcs, sources=sources)
    assert b.schema_version == "2.6"
    assert b.h1 == "How Retatrutide Works" and b.title == b.h1
    assert b.intent_type == "how-to" and b.intent_review_required is False
    assert b.format_directives.min_h2_body_words == 150          # sequential_steps floor
    # H1 + 2 MCS H2s
    levels = [(h.level, h.order) for h in b.heading_structure]
    assert levels == [("H1", 1), ("H2", 2), ("H2", 3)]
    assert b.heading_structure[1].text == "Retatrutide activates GLP-1"
    assert len(b.discarded_headings) == 1
    assert b.metadata["main_entity"]["canonical"] == "retatrutide"
    assert b.metadata["mcs"]["selected_count"] == 2


def test_build_brief_output_interleaves_authority_h3s():
    intent = _intent("informational")
    title = TitleScope(title="T", scope_statement="Covers x. Does not cover y.")
    entity = MainEntity(canonical="e")
    mcs = MCSResult(
        selected=[ScoredHeading("H2 one", [0.9], 0.8, 0.9, 0.85),
                  ScoredHeading("H2 two", [0.8], 0.7, 0.8, 0.75)],
        pool=["a"], discarded=[])
    authority = [
        {"text": "deep H3", "parent_h2_text": "H2 one", "scope_alignment_note": "in scope"},
        {"text": "extra H3", "parent_h2_text": "H2 one"},
        {"text": "third H3", "parent_h2_text": "H2 one"},          # >2 -> dropped
        {"text": "orphan", "parent_h2_text": "nope"},               # no parent -> dropped
    ]
    b = build_brief_output(keyword="k", intent=intent, title=title, entity=entity, mcs=mcs,
                           sources=BriefSources(keyword="k"), authority_h3s=authority)
    assert [(h.level, h.text) for h in b.heading_structure] == [
        ("H1", "T"), ("H2", "H2 one"), ("H3", "deep H3"), ("H3", "extra H3"), ("H2", "H2 two")]
    assert [h.order for h in b.heading_structure] == [1, 2, 3, 4, 5]
    h3 = b.heading_structure[2]
    assert h3.source == "authority_gap_sme" and h3.parent_h2_text == "H2 one" and h3.exempt is True


def test_generate_authority_gaps_restricts_parent_to_h2s():
    from app.briefgen.authority import generate_authority_gaps

    class _LLM:
        def call_tool(self, **kw):
            return {"h3s": [
                {"text": "valid", "parent_h2_text": "H2 a", "scope_alignment_note": "n"},
                {"text": "bad parent", "parent_h2_text": "not an h2"},   # dropped
                {"text": "", "parent_h2_text": "H2 a"},                  # empty -> dropped
            ]}

    out = generate_authority_gaps("k", title="t", scope_statement="s", intent_type="informational",
                                  h2_texts=["H2 a", "H2 b"], reddit_summaries=[], llm=_LLM())
    assert out == [{"text": "valid", "parent_h2_text": "H2 a", "scope_alignment_note": "n"}]
    # no H2s -> no call, empty
    assert generate_authority_gaps("k", title="t", scope_statement="s", intent_type="x",
                                   h2_texts=[], reddit_summaries=[], llm=_LLM()) == []


# ----- generate_brief wiring (all deps stubbed) -----------------------------


def _vec(text: str):
    # deterministic distinct unit vector per text, so gates/MCS produce real variation.
    h = int(hashlib.md5(text.encode()).hexdigest(), 16) % 997
    ang = h / 997 * 2 * math.pi
    return [math.cos(ang), math.sin(ang)]


def _embed(texts):
    return [_vec(t) for t in texts]


class _DFS:
    def serp_advanced_items(self, keyword, depth=20):
        return [
            {"type": "organic", "url": "https://a.com", "title": "Retatrutide explained", "description": "d", "rank_absolute": 1},
            {"type": "ai_overview", "text": "Retatrutide is a triple agonist. It targets GLP-1, GIP and glucagon. It drives weight loss."},
            {"type": "people_also_ask", "items": [{"title": "is retatrutide approved?"}]},
        ]

    def autocomplete(self, keyword):
        return ["retatrutide dose"]

    def keyword_suggestions(self, keyword):
        return ["retatrutide results"]

    def llm_response_items(self, prompt, provider):
        return [{"text": f"{provider} says retatrutide is a triple agonist for weight loss."}]


class _LLM:
    def __init__(self, payload):
        self.payload = payload

    def call_tool(self, **kw):
        p = self.payload
        return p(kw) if callable(p) else p


def test_generate_brief_wires_end_to_end():
    gen = _LLM(lambda kw: {"headings": [
        "Retatrutide activates the GLP-1 receptor",
        "Retatrutide adds GIP agonism",
        "Retatrutide engages the glucagon receptor",
        "Retatrutide drives double-digit weight loss",
        "Retatrutide is dosed weekly",
    ]})
    intent = _LLM({"intent_type": "informational", "intent_confidence": 0.9,
                   "decision_fit_detection": {"is_multi_answer": False, "confidence": 0.1}})
    title = _LLM({"title": "How Retatrutide Works", "scope_statement": "Explains it. Does not cover dosing.",
                  "title_rationale": "r"})
    deps = BriefDeps(
        dfs=_DFS(), scrapeowl=None, np_extract=lambda text: [],
        embed_3large=_embed, embed_aio_query=_embed, embed_aio_doc=_embed,
        gen_llm=gen, intent_llm=intent, title_llm=title,
    )
    b = generate_brief("retatrutide", location_code=2840, deps=deps)
    assert b.keyword == "retatrutide"
    assert b.h1 == "How Retatrutide Works" and b.title == b.h1
    assert b.intent_type == "informational"
    assert "does not cover" in b.scope_statement.lower()
    assert b.heading_structure and b.heading_structure[0].level == "H1"
    assert b.metadata["mcs"]["aio_present"] is True and b.metadata["mcs"]["chatgpt_present"] is True
