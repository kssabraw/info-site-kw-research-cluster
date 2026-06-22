"""M14 slice 4 — pipeline wiring (F-A: degraded 1.7-no-context, all deps mocked)."""

import hashlib
import math

from app.writer.adapter import build_writer_inputs
from app.writer.pipeline import WriterDeps, generate_article


def _vec(text: str):
    h = int(hashlib.md5(text.encode()).hexdigest(), 16) % 997
    ang = h / 997 * 2 * math.pi
    return [math.cos(ang), math.sin(ang)]


def _embed(texts):
    return [_vec(t) for t in texts]


class _LLM:
    """Mock Anthropic client: complete_text returns canned prose; call_tool returns a
    payload keyed by tool_name (or computed from the user prompt)."""

    def __init__(self, *, tool_payloads=None, prose="A direct answer sentence here. "
                 "Supporting detail follows in plain language. More elaboration to close."):
        self._tool = tool_payloads or {}
        self._prose = prose

    def complete_text(self, *, system, user, purpose, max_tokens=None, temperature=None):
        if purpose == "writer_enrichment_lede":
            return "Retatrutide is an investigational triple-agonist medication studied for weight loss."
        if purpose == "writer_conclusion":
            return ("In summary, is retatrutide a glp-3 drug is best understood through its "
                    "triple-agonist mechanism and ongoing trials. The evidence continues to evolve.")
        # section prose, repeated to clear the body-length floor
        return self._prose * 12

    def call_tool(self, *, system, user, tool_name, tool_description, input_schema,
                  purpose, max_tokens=None, temperature=None):
        if tool_name in self._tool:
            return self._tool[tool_name]
        if tool_name == "intro":
            return {"agree": "You are weighing whether this drug fits your needs.",
                    "promise": "This article explains the mechanism and current status.",
                    "preview": "We cover the mechanism, trial status, and naming."}
        if tool_name == "faqs":
            qs = [ln[2:] for ln in user.splitlines() if ln.startswith("- ")]
            return {"faqs": [{"question": q, "answer": "A self-contained answer about retatrutide "
                              "that stands alone and is answer-first in forty to eighty words here."}
                             for q in qs]}
        if tool_name == "takeaways":
            return {"takeaways": [
                "Retatrutide is a triple agonist targeting GLP-1, GIP, and glucagon receptors.",
                "It remains investigational and is studied primarily for weight loss.",
                "The GLP-3 label is informal, not an official drug classification.",
            ]}
        if tool_name == "cta":
            return {"cta": "Explore the related sub-topics next."}
        return {}


def _brief_json():
    return {
        "keyword": "is retatrutide a glp-3 drug",
        "title": "Is Retatrutide a GLP-3 Drug? The Triple-Agonist Mechanism Explained",
        "intent_type": "informational",
        "scope_statement": "Explains the mechanism and naming. Does not cover dosing.",
        "heading_structure": [
            {"order": 1, "level": "H1", "text": "Is Retatrutide a GLP-3 Drug?", "type": "content"},
            {"order": 2, "level": "H2", "text": "Retatrutide is a triple-agonist medication", "type": "content"},
            {"order": 3, "level": "H3", "text": "How GLP-1, GIP, and glucagon receptors differ", "type": "content",
             "parent_h2_text": "Retatrutide is a triple-agonist medication"},
            {"order": 4, "level": "H2", "text": "Retatrutide is informally called a GLP-3 drug", "type": "content"},
            {"order": 5, "level": "H2", "text": "Retatrutide remains in clinical trials", "type": "content"},
        ],
        "faqs": [{"question": "Is retatrutide FDA approved?", "faq_score": 0.9},
                 {"question": "What receptors does retatrutide target?", "faq_score": 0.85},
                 {"question": "Is GLP-3 a real drug class?", "faq_score": 0.8}],
        "format_directives": {"require_tables": False, "min_h2_body_words": 120},
        "metadata": {},
    }


def _sie_json():
    return {
        "schema_version": "1.4", "keyword": "is retatrutide a glp-3 drug",
        "word_count": {"target": 2500, "min": 2000, "max": 3000},
        "target_keyword": {"term": "is retatrutide a glp-3 drug",
                           "minimum_usage": {"h2": 1, "h3": 0, "paragraphs": 6}},
        "terms": {"required": [
            {"term": "glp-1 receptor", "recommendation_score": 0.9, "is_entity": True,
             "entity_category": "Drug Class"},
            {"term": "weight loss", "recommendation_score": 0.8, "is_entity": False}], "avoid": []},
        "usage_recommendations": [],
        "entities": [{"term": "retatrutide", "entity_category": "Drug", "recommendation_score": 0.95}],
    }


def test_generate_article_end_to_end_degraded():
    brief, sie, warnings = build_writer_inputs(_brief_json(), _sie_json())
    deps = WriterDeps(section_llm=_LLM(), short_llm=_LLM(), embed_fn=_embed)
    out = generate_article(brief, sie, warnings=warnings, deps=deps, word_budget=2500)

    assert out.keyword == "is retatrutide a glp-3 drug"
    assert out.client_context_summary["schema_version_effective"] == "1.7-no-context"
    assert out.metadata["no_citations"] is True
    # display order: H1 first, then key-takeaways, then intro
    types = [(i.level, i.type) for i in out.article]
    assert types[0] == ("H1", "title")
    assert any(t == ("none", "key-takeaways") for t in types)
    assert any(t == ("none", "intro") for t in types)
    # FAQ header + conclusion + CTA present
    assert any(i.type == "faq-header" for i in out.article)
    assert any(i.type == "conclusion" for i in out.article)
    assert out.article[-1].type == "cta"
    # serialized outputs, no citation markers in degraded mode
    assert out.article_markdown.startswith("# ")
    assert "{{cit_" not in out.article_markdown and "<sup>" not in out.article_html
    assert "## Sources" not in out.article_markdown
    assert out.metadata["faq_count"] == 3
    assert out.metadata["section_count"] >= 1
    assert out.key_takeaways and len(out.key_takeaways) >= 3
    assert out.metadata["total_word_count"] > 0


def test_group_to_items_promotes_lead_when_model_starts_with_h3():
    from app.writer.budget import Group
    from app.writer.models import BriefHeading
    from app.writer.pipeline import _group_to_items

    group = Group(parent=BriefHeading(order=1, level="H2", text="The H2"),
                  children=[BriefHeading(order=2, level="H3", text="Sub A")])

    # Model led straight into a ### subheading (no H2 lead paragraph).
    prose = "### Sub A\nFirst paragraph of real content.\n\n### Sub B\nMore content."
    items = _group_to_items(prose, group, 100)
    kinds = [(it.level, it.type, it.heading, bool(it.body)) for it in items]
    # H2 heading, then a promoted lead BODY (not an H3), then the remaining H3
    assert kinds[0][:2] == ("H2", "content")
    assert kinds[1] == ("none", "content", None, True)        # promoted lead paragraph
    assert items[1].body.startswith("First paragraph")
    # the first restating "### Sub A" heading was dropped; "Sub B" survives as an H3
    assert any(it.level == "H3" and it.heading == "Sub B" for it in items)
    assert not any(it.level == "H3" and it.heading == "Sub A" for it in items)
    # invariant: no H2 is immediately followed by an H3
    levels = [it.level for it in items]
    for i, lvl in enumerate(levels[:-1]):
        if lvl == "H2":
            assert levels[i + 1] != "H3"


def test_group_to_items_normal_lead_then_h3():
    from app.writer.budget import Group
    from app.writer.models import BriefHeading
    from app.writer.pipeline import _group_to_items

    group = Group(parent=BriefHeading(order=1, level="H2", text="The H2"),
                  children=[BriefHeading(order=2, level="H3", text="Sub A")])
    prose = "Answer-first lead paragraph here.\n\n### Sub A\nSubsection content."
    items = _group_to_items(prose, group, 100)
    assert items[1].level == "none" and items[1].body.startswith("Answer-first")
    assert any(it.level == "H3" and it.heading == "Sub A" for it in items)


def test_generate_article_drops_low_adherence_h2():
    # An off-topic H2 whose title-cosine falls below 0.62 is dropped.
    bj = _brief_json()
    bj["heading_structure"].append(
        {"order": 6, "level": "H2", "text": "Completely unrelated gardening tips", "type": "content"})
    brief, sie, warnings = build_writer_inputs(bj, _sie_json())

    # Force the off-topic H2 far from the title; keep the rest near.
    title = brief.title

    def embed(texts):
        out = []
        for t in texts:
            if "gardening" in t:
                out.append([0.0, 1.0])
            elif t == title:
                out.append([1.0, 0.0])
            else:
                out.append([0.98, 0.2])
        return out

    deps = WriterDeps(section_llm=_LLM(), short_llm=_LLM(), embed_fn=embed)
    out = generate_article(brief, sie, warnings=warnings, deps=deps, word_budget=2500)
    dropped = out.metadata["dropped_for_low_topic_adherence"]
    assert any("gardening" in d["heading"] for d in dropped)
