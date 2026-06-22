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
