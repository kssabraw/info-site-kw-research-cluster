"""M13 slice 3 — eligibility-gate pre-filter (X.3) pure tests (injected embed_fn)."""

from app.briefgen.entity import MainEntity
from app.briefgen.gates import prefilter, strip_entity


def _embed(mapping, default=(0.0, 0.0, 1.0)):
    return lambda texts: [list(mapping.get(t, default)) for t in texts]


def test_strip_entity_removes_canonical_and_variants():
    me = MainEntity(canonical="retatrutide", variants=["reta"])
    assert strip_entity("How retatrutide works", me) == "How works"
    assert strip_entity("Is RETA safe?", me) == "Is safe?"
    assert strip_entity("dosing schedule", me) == "dosing schedule"   # untouched


def test_relevance_floor_rejects_offtopic():
    me = MainEntity(canonical="retatrutide")
    res = prefilter(
        ["Off-topic zodiac heading"], topic_vec=[1, 0, 0], references=[], main_entity=me,
        embed_fn=_embed({"Off-topic zodiac heading": (0, 1, 0)}),   # cosine 0 < 0.55
    )
    assert res[0].passed is False and res[0].reason == "below_relevance_floor"


def test_restatement_ceiling_uses_entity_stripped_text():
    """Collision §4.5-A: two headings that overlap ONLY via the shared entity must NOT
    be flagged as restatements — stripping the entity makes their residuals distinct."""
    me = MainEntity(canonical="retatrutide")
    cand = "How retatrutide is dosed"
    ref = "How retatrutide works"
    embed = _embed({
        # full headings look similar (shared entity) — but the gate must use stripped text
        cand: (1, 0, 0),
        # stripped residuals are distinct -> low restatement -> passes
        "How is dosed": (1, 0, 0),
        "How works": (0, 1, 0),
    })
    res = prefilter([cand], topic_vec=[1, 0, 0], references=[ref], main_entity=me, embed_fn=embed)
    assert res[0].passed is True                      # not a restatement after stripping
    assert res[0].restatement <= 0.78


def test_restatement_ceiling_rejects_true_duplicate():
    me = MainEntity(canonical="retatrutide")
    cand = "How retatrutide is dosed"
    ref = "Dosing retatrutide correctly"
    embed = _embed({
        cand: (1, 0, 0),
        "How is dosed": (1, 0, 0),
        "Dosing correctly": (1, 0, 0),   # residuals near-identical -> restatement ~1 > 0.78
    })
    res = prefilter([cand], topic_vec=[1, 0, 0], references=[ref], main_entity=me, embed_fn=embed)
    assert res[0].passed is False and res[0].reason == "restates_existing"
