"""M14 slice 3 — pure core: budget, validators (claims/soften/CTA/takeaways), serialize.

Maps to the PRD §14 fixtures F-L/F-M/F-N/F-O/F-R/F-S/F-T/F-U where applicable.
"""

from app.writer.budget import allocate_budget, drop_low_adherence, group_headings
from app.writer.models import ArticleItem, BriefHeading, IntentType
from app.writer.serialize import plain_text, to_html, to_markdown
from app.writer.templates import cta_template, h2_body_floor
from app.writer.validators import (
    coverage_ratio,
    detect_citable_claims,
    fallback_cta,
    normalize_takeaways,
    overlong_takeaways,
    paragraph_violations,
    soften_operational_claims,
    split_sentences,
    titlecase_heading,
    truncate_cta,
    validate_cta,
    word_count,
)


def _h(order, level, text, type="content", source=None):
    return BriefHeading(order=order, level=level, text=text, type=type, source=source)


# ----- templates ------------------------------------------------------------

def test_h2_body_floor_brief_wins_else_intent():
    assert h2_body_floor(IntentType.informational, 0) == 180   # intent floor
    assert h2_body_floor(IntentType.informational, 220) == 220  # brief wins
    assert h2_body_floor(IntentType.listicle, 0) == 80


def test_cta_template_per_intent():
    assert "steps" in cta_template(IntentType.how_to)
    assert "follow-on coverage" in cta_template(IntentType.news)


# ----- budget allocation (§5.4.1) -------------------------------------------

def test_group_headings_attaches_h3_to_h2():
    hs = [_h(1, "H1", "T"), _h(2, "H2", "A"), _h(3, "H3", "a1"), _h(4, "H2", "B")]
    groups = group_headings(hs)
    assert len(groups) == 2
    assert groups[0].parent.text == "A" and [c.text for c in groups[0].children] == ["a1"]
    assert groups[1].children == []


def test_allocate_budget_equal_groups_plus_conclusion_and_floor():
    hs = [_h(1, "H2", "A"), _h(2, "H2", "B"), _h(10, "H2", "Conclusion", type="conclusion")]
    alloc = allocate_budget(hs, word_budget=2500, conclusion_budget=125)
    # body 2375 / 2 groups = ~1188 each
    assert alloc[1] == alloc[2] and abs(alloc[1] - 1188) <= 1
    assert alloc[10] == 125


def test_allocate_budget_authority_gap_weight_pulls_within_group():
    hs = [_h(1, "H2", "A"), _h(2, "H3", "reg"), _h(3, "H3", "auth", source="authority_gap_sme")]
    alloc = allocate_budget(hs, word_budget=2500, conclusion_budget=0)
    # one group, body 2500; weights 1.0/1.0/1.2 -> auth H3 gets the largest share
    assert alloc[3] > alloc[2] and alloc[2] == alloc[1]


def test_allocate_budget_section_floor():
    hs = [_h(i, "H2", f"H{i}") for i in range(1, 60)]   # many tiny groups
    alloc = allocate_budget(hs, word_budget=2500)
    assert min(alloc.values()) >= 50


# ----- adherence filter (§5.4.2) — F-J/F-K ----------------------------------

def test_drop_low_adherence_keeps_above_drops_below():
    hs = [_h(1, "H2", "keep"), _h(2, "H3", "keep-child"), _h(3, "H2", "drop")]
    kept, dropped = drop_low_adherence(hs, {1: 0.80, 3: 0.40}, threshold=0.62)
    assert set(kept) == {1, 2}
    assert dropped == [{"order": 3, "heading": "drop", "score": 0.4}]


# ----- sentence / paragraph (§5.13) — F-Q -----------------------------------

def test_split_sentences_skips_abbreviations():
    s = split_sentences("The U.S. market grew. Dr. Lee agrees, e.g. on pricing. Done.")
    assert len(s) == 3


def test_paragraph_violations_over_cap():
    body = "One. Two. Three. Four. Five.\n\nShort one. Short two."
    v = paragraph_violations(body, max_sentences=4)
    assert v == [{"paragraph_index": 0, "sentence_count": 5}]


# ----- citable claims (§5.8.8) — F-M/F-N/F-O --------------------------------

def test_detect_citable_claims_patterns():
    text = ("Demand climbed 18% in Q3 of 2023. According to Reuters the trend holds. "
            "Use a 4-to-6 week refresh cadence. Apply the 5% rule. Run a weekly audit.")
    claims = detect_citable_claims(text)
    flat = {p for c in claims for p in c.patterns}
    assert "C1" in flat and "C3" in flat and "C4" in flat
    assert "C7" in flat and "C9" in flat and "C8" in flat


def test_c6_requires_entity_plus_qualifier():
    text = "Retatrutide reduced weight by 24% in trials."
    assert any("C6" in c.patterns for c in detect_citable_claims(text, entities=["retatrutide"]))
    # same sentence without the entity registered -> no C6 (still C1 from the %)
    assert not any("C6" in c.patterns for c in detect_citable_claims(text, entities=[]))


def test_soften_c7_c9_but_not_c1():
    # F-O: C1 "18% in Q3" must NOT be softened
    text, n = soften_operational_claims("Demand climbed 18% in Q3.")
    assert text == "Demand climbed 18% in Q3." and n == 0
    # F-M: C7 duration softened
    t7, n7 = soften_operational_claims("Use a 4-to-6 week refresh cadence here.")
    assert "typical refresh cadence" in t7 and n7 == 1
    # F-N: C9 "5% rule" softened
    t9, n9 = soften_operational_claims("Apply the 5% rule strictly.")
    assert "a small percentage rule" in t9 and n9 == 1


def test_coverage_ratio_no_citations_is_under_floor():
    citable, cited, ratio = coverage_ratio("Demand rose 18% last year.")
    assert citable >= 1 and cited == 0 and ratio == 0.0
    # a section with no citable claims is trivially covered
    assert coverage_ratio("Retatrutide is a medication.")[2] == 1.0


# ----- CTA (§5.11) — F-R ----------------------------------------------------

def test_validate_and_truncate_cta():
    assert validate_cta("Explore the related sub-topics next.")["ok"] is True
    hard = validate_cta("Buy now while supplies last.")
    assert hard["ok"] is False and hard["hard_sales"] is True
    long_cta = " ".join(["word"] * 35)
    v = validate_cta(long_cta)
    assert v["too_long"] is True
    assert len(truncate_cta(long_cta).split()) <= 30
    assert "steps" in fallback_cta(IntentType.how_to)


# ----- Key Takeaways (§5.12) — F-S/F-T --------------------------------------

def test_normalize_takeaways_truncate_and_abort():
    six = [f"t{i}" for i in range(6)]
    items, code = normalize_takeaways(six)
    assert len(items) == 5 and code is None              # F-S truncate to 5
    items2, code2 = normalize_takeaways(["only", "two"])
    assert code2 == "key_takeaways_count_invalid"         # F-T abort <3


def test_overlong_takeaways_flags_index():
    long_one = " ".join(["w"] * 30)
    assert overlong_takeaways(["short", long_one]) == [1]


# ----- title-case (§5.18) ---------------------------------------------------

def test_titlecase_idempotent_and_safe():
    once = titlecase_heading("how retatrutide works")
    assert titlecase_heading(once) == once               # idempotent
    assert titlecase_heading("") == ""


# ----- serialization (§5.19) — F-U ------------------------------------------

def test_serialize_round_trip_no_markers():
    article = [
        ArticleItem(order=1, level="H1", type="title", heading="Is Retatrutide a GLP-3 Drug?"),
        ArticleItem(order=2, level="none", type="key-takeaways", heading="Key Takeaways",
                    body="- It is a triple agonist\n- It is in trials"),
        ArticleItem(order=3, level="H2", type="content", heading="How it works"),
        ArticleItem(order=4, level="none", type="content", body="Retatrutide hits three receptors."),
    ]
    md = to_markdown(article)
    html_out = to_html(article)
    assert md.startswith("# Is Retatrutide a GLP-3 Drug?")
    assert "## Key Takeaways" in md and "## How it works" in md
    assert "## Sources" not in md                          # no citations -> no Sources
    assert "<h1>Is Retatrutide a GLP-3 Drug?</h1>" in html_out
    assert "{{cit_" not in md and "<sup>" not in html_out
    # round-trip: plain text recovers the body content (§5.19.4)
    assert "Retatrutide hits three receptors." in plain_text(article)


def test_serialize_html_escapes_body():
    article = [ArticleItem(order=1, level="none", type="content", body="A < B & C > D")]
    assert "&lt; B &amp; C &gt;" in to_html(article)


def test_serialize_empty_article():
    assert to_markdown([]) == "" and to_html([]) == ""


def test_word_count_strips_markers():
    assert word_count("Demand rose sharply {{cit_007}} last year.") == 5
