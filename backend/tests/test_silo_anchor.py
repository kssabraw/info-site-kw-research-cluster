"""Enriched silo anchors — demo-keyword centroid (routing calibration).

Pure unit coverage of the centroid math + the orchestration layer. The LLM and
embed calls are monkeypatched, so no egress.
"""

import math

from app.pipeline.silo_anchor import build_enriched_anchors, compute_centroid


def _vec(*xs: float) -> list[float]:
    return list(xs)


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class _FakeLLM:
    def __init__(self, examples_by_name: dict[str, list[str]]):
        self.examples_by_name = examples_by_name
        self.calls: list[tuple[str, str]] = []

    def silo_anchor_examples(self, *, seed, silo_name, rationale,
                             relationship_type, peer_terms, n):
        self.calls.append((seed, silo_name))
        return list(self.examples_by_name.get(silo_name, []))[:n]


def test_centroid_is_unit_normalized():
    """The centroid of unit vectors must itself be unit-normalized; the gate's
    cosine routing assumes anchors are unit vectors."""
    result = compute_centroid(_vec(1, 0), [_vec(0, 1), _vec(0, 1)])
    norm = math.sqrt(_dot(result, result))
    assert abs(norm - 1.0) < 1e-9


def test_centroid_pulls_toward_examples():
    """The centroid should be closer to the example direction than to the
    rationale direction (when there are multiple aligned examples) — that's
    what makes the enriched anchor more discriminative."""
    rationale = _vec(1, 0)
    examples = [_vec(0, 1), _vec(0, 1), _vec(0, 1)]  # 3 examples one direction
    centroid = compute_centroid(rationale, examples)
    # Should have y > x (pulled toward examples).
    assert centroid[1] > centroid[0]


def test_centroid_falls_back_to_rationale_when_no_examples():
    rationale = _vec(0.6, 0.8)
    centroid = compute_centroid(rationale, [])
    norm = math.sqrt(_dot(centroid, centroid))
    assert abs(norm - 1.0) < 1e-9
    # Direction preserved (just unit-normalized).
    assert abs(centroid[0] / centroid[1] - 0.6 / 0.8) < 1e-9


def test_build_enriched_anchors_centroids_with_rationale():
    silos = [
        {"id": "s1", "name": "Mechanism", "rationale": "how it works"},
        {"id": "s2", "name": "Safety", "rationale": "side effects"},
    ]
    rationales = {"s1": [1.0, 0.0], "s2": [0.0, 1.0]}
    # Each silo's examples lie in its rationale direction (cleanly separable).
    examples = {"Mechanism": ["mech a", "mech b"], "Safety": ["safe a", "safe b"]}
    llm = _FakeLLM(examples)
    embed_map = {
        "mech a": [1.0, 0.0], "mech b": [1.0, 0.0],
        "safe a": [0.0, 1.0], "safe b": [0.0, 1.0],
    }

    def embed(batch):
        return [embed_map[k] for k in batch]

    anchors, counts = build_enriched_anchors(
        seed="thing", silos=silos, rationale_embeddings=rationales,
        peer_terms=[], llm=llm, embed_fn=embed, n=2, max_workers=2,
    )

    # Anchors should still cleanly separate the two silos (centroid stays
    # aligned with the consistent rationale + examples direction).
    assert _dot(anchors["s1"], [1, 0]) > 0.99
    assert _dot(anchors["s2"], [0, 1]) > 0.99
    assert counts == {"s1": 2, "s2": 2}


def test_silo_with_failed_examples_falls_back_to_rationale():
    silos = [{"id": "s1", "name": "Mech", "rationale": "x"}]
    rationales = {"s1": [0.6, 0.8]}
    # LLM returns nothing for this silo (simulated failure path).
    anchors, counts = build_enriched_anchors(
        seed="thing", silos=silos, rationale_embeddings=rationales,
        peer_terms=[], llm=_FakeLLM({}), embed_fn=lambda b: [],
        n=10, max_workers=1,
    )
    # Falls back to the rationale embedding unchanged.
    assert anchors["s1"] == [0.6, 0.8]
    assert counts == {"s1": 0}


def test_silo_without_rationale_embedding_is_skipped():
    """A silo missing a rationale embedding shouldn't appear in the anchor map
    (no foundation to build on); the caller writes back nothing for it."""
    silos = [{"id": "s1", "name": "ok", "rationale": "r1"},
             {"id": "s2", "name": "missing", "rationale": "r2"}]
    rationales = {"s1": [1.0, 0.0]}  # s2 missing
    anchors, counts = build_enriched_anchors(
        seed="thing", silos=silos, rationale_embeddings=rationales,
        peer_terms=[], llm=_FakeLLM({"ok": ["k1"], "missing": ["k2"]}),
        embed_fn=lambda b: [[1.0, 0.0]] * len(b),
        n=1, max_workers=1,
    )
    assert "s1" in anchors
    assert "s2" not in anchors


def test_partial_embed_failure_drops_to_rationale_only():
    """If the embed call returns a count != requested, we don't half-enrich —
    fall back to rationale-only anchors for safety."""
    silos = [{"id": "s1", "name": "X", "rationale": "r"}]
    rationales = {"s1": [0.0, 1.0]}

    def embed(batch):
        return [[1.0, 0.0]]  # only 1 returned but we asked for 2

    anchors, counts = build_enriched_anchors(
        seed="thing", silos=silos, rationale_embeddings=rationales,
        peer_terms=[], llm=_FakeLLM({"X": ["a", "b"]}), embed_fn=embed,
        n=2, max_workers=1,
    )
    assert anchors["s1"] == [0.0, 1.0]
    assert counts["s1"] == 0
