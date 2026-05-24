"""Session endpoints: silo discovery (M2) + keyword pipeline (M3/M4).

Lifecycle: create a session (grounding + proposal), optionally resolve
disambiguation, review/edit silos, finalize (embeds each silo), pick which silos
to deep-mine (§7.2), then run /expand — which now runs the full refinement
pipeline: expansion + competitor mining + relevance gate + statistical clustering.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import AuthedUser, require_user
from app.config import get_settings
from app.dataforseo import get_dataforseo
from app.llm import LLMError, get_llm
from app.logging import bind_session_id
from app.pipeline.models import PROPOSABLE_TYPES, RelationshipType
from app.pipeline.orchestrate import PipelineTopic, run_refinement_pipeline
from app.pipeline.silo_discovery import run_silo_discovery
from app.storage import silo as store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sessions"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class CreateSessionBody(BaseModel):
    seed_keyword: str = Field(min_length=1, max_length=200)
    project_id: str | None = None
    audience_hint: str | None = None
    disambiguation_hint: str | None = None
    topic_count: int = Field(default=5, ge=3, le=10)
    coverage_mode: str = Field(default="standard", pattern="^(standard|comprehensive)$")


class DisambiguateBody(BaseModel):
    choice: str = Field(min_length=1, max_length=200)


class OverrideAudienceBody(BaseModel):
    detected_audience: str = Field(min_length=1, max_length=400)


class AddTopicBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rationale: str | None = None
    relationship_type: RelationshipType = RelationshipType.property_or_mechanism
    is_broader_class: bool = False


class EditTopicBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    rationale: str | None = None
    relationship_type: RelationshipType | None = None


class DeepMineBody(BaseModel):
    # Silos the user chose to mine for competitor keywords (PRD §7.2). The seed
    # is always mined regardless; an empty list means "seed only".
    topic_ids: list[str] = Field(default_factory=list)


class SiloDiscoveryResponse(BaseModel):
    session_id: str
    status: str
    detected_audience: str | None = None
    needs_disambiguation: bool = False
    interpretations: list[str] = []
    degraded_notes: list[str] = []
    silos: list[dict] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_session(user: AuthedUser, session_id: str) -> dict:
    session = store.session_visible_to_user(user.access_token, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _run_and_persist(session: dict) -> SiloDiscoveryResponse:
    """Run silo discovery for a session and persist the outcome."""
    settings = session.get("settings") or {}
    coverage_mode = settings.get("coverage_mode", "standard")
    try:
        result = run_silo_discovery(
            seed=session["seed_keyword"],
            topic_count=int(settings.get("topic_count", 5)),
            audience_hint=session.get("audience_hint"),
            disambiguation_hint=session.get("disambiguation_hint")
            or session.get("disambiguation_choice"),
            llm=get_llm(),
            dfs=get_dataforseo(),
            serp_top_n=10 if coverage_mode == "comprehensive" else 5,
            ambiguity_separation_threshold=get_settings().ambiguity_separation_threshold,
        )
    except LLMError as exc:
        store.update_session(session["id"], {"status": "error"})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Silo discovery could not complete: {exc}",
        ) from exc

    store.update_session(session["id"], {"detected_audience": result.detected_audience})

    if result.needs_disambiguation:
        return SiloDiscoveryResponse(
            session_id=session["id"],
            status="running_pre_review",
            detected_audience=result.detected_audience,
            needs_disambiguation=True,
            interpretations=result.interpretations,
        )

    store.delete_topics_for_session(session["id"])
    topics = store.insert_proposed_topics(session["id"], result.silos)
    store.update_session(session["id"], {"status": "awaiting_silo_review"})
    return SiloDiscoveryResponse(
        session_id=session["id"],
        status="awaiting_silo_review",
        detected_audience=result.detected_audience,
        degraded_notes=result.degraded_notes,
        silos=store.list_topics(session["id"]) if topics is not None else [],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/sessions", response_model=SiloDiscoveryResponse)
def create_session(
    body: CreateSessionBody, user: AuthedUser = Depends(require_user)
) -> SiloDiscoveryResponse:
    # A supplied project must be one the caller can see (RLS), else the session
    # would attach to a project they don't own (PRD §13).
    if body.project_id and not store.project_visible_to_user(
        user.access_token, body.project_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    project_id = store.resolve_project_id(user.id, body.project_id)
    session = store.create_session(
        user_id=user.id,
        project_id=project_id,
        seed_keyword=body.seed_keyword.strip(),
        audience_hint=body.audience_hint,
        disambiguation_hint=body.disambiguation_hint,
        settings={
            "topic_count": body.topic_count,
            "coverage_mode": body.coverage_mode,
            "recursive_fanout": False,
            "enrich_with_metrics": False,
        },
    )
    bind_session_id(session["id"])
    return _run_and_persist(session)


@router.post("/sessions/{session_id}/disambiguate", response_model=SiloDiscoveryResponse)
def disambiguate(
    session_id: str, body: DisambiguateBody, user: AuthedUser = Depends(require_user)
) -> SiloDiscoveryResponse:
    session = _require_session(user, session_id)
    bind_session_id(session_id)
    session = store.update_session(session_id, {"disambiguation_choice": body.choice.strip()})
    return _run_and_persist(session)


@router.get("/sessions/{session_id}", response_model=SiloDiscoveryResponse)
def get_session(
    session_id: str, user: AuthedUser = Depends(require_user)
) -> SiloDiscoveryResponse:
    session = _require_session(user, session_id)
    bind_session_id(session_id)
    return SiloDiscoveryResponse(
        session_id=session_id,
        status=session["status"],
        detected_audience=session.get("detected_audience"),
        silos=store.list_topics(session_id),
    )


@router.patch("/sessions/{session_id}/audience", response_model=SiloDiscoveryResponse)
def override_audience(
    session_id: str, body: OverrideAudienceBody, user: AuthedUser = Depends(require_user)
) -> SiloDiscoveryResponse:
    session = _require_session(user, session_id)
    bind_session_id(session_id)
    session = store.update_session(
        session_id, {"detected_audience": body.detected_audience.strip()}
    )
    return SiloDiscoveryResponse(
        session_id=session_id,
        status=session["status"],
        detected_audience=session.get("detected_audience"),
        silos=store.list_topics(session_id),
    )


@router.post("/sessions/{session_id}/finalize")
def finalize_silos(session_id: str, user: AuthedUser = Depends(require_user)) -> dict:
    session = _require_session(user, session_id)
    bind_session_id(session_id)
    topics = store.list_topics(session_id)
    if not topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No silos to finalize. Add at least one silo first.",
        )

    seed = session["seed_keyword"]
    audience = session.get("detected_audience") or ""
    # Anchor string per PRD §7.1.4: seed + rationale + audience.
    texts = [
        " ".join(part for part in (seed, t.get("rationale") or "", audience) if part).strip()
        for t in topics
    ]
    try:
        vectors = get_llm().embed(texts)
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Embedding the silos failed. Try finalizing again.",
        ) from exc

    for topic, vector in zip(topics, vectors):
        store.set_topic_embedding(topic["id"], vector)

    logger.info(
        "step_complete",
        extra={"event": "step_complete", "step": "silo_finalize", "topic_count": len(topics)},
    )
    return {"finalized": True, "topic_count": len(topics)}


# ---- M4 deep-mine selection (PRD §7.2) ------------------------------------
@router.post("/sessions/{session_id}/deep-mine")
def set_deep_mine(
    session_id: str, body: DeepMineBody, user: AuthedUser = Depends(require_user)
) -> dict:
    """Record which silos to mine for competitor keywords. The seed is always
    mined; this only gates the additional silos."""
    _require_session(user, session_id)
    bind_session_id(session_id)
    valid_ids = {t["id"] for t in store.list_topics(session_id)}
    requested = list(dict.fromkeys(body.topic_ids))  # dedupe, preserve order
    invalid = [tid for tid in requested if tid not in valid_ids]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Topics do not belong to this session: {', '.join(invalid)}",
        )
    store.set_topics_gating(session_id, requested)
    return {"gated_topic_ids": requested, "topics": store.list_topics(session_id)}


# ---- M3 expansion + M4 mining/relevance/clustering ------------------------
@router.post("/sessions/{session_id}/expand")
def expand_session(session_id: str, user: AuthedUser = Depends(require_user)) -> dict:
    session = _require_session(user, session_id)
    bind_session_id(session_id)
    topics = store.list_topics(session_id)
    if not topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No silos to expand. Finalize at least one silo first.",
        )

    seed = session["seed_keyword"]
    embeddings = store.get_topic_embeddings(session_id)
    store.update_session(session_id, {"status": "running"})
    s = get_settings()
    coverage_mode = (session.get("settings") or {}).get("coverage_mode", "standard")
    top_n = (
        s.competitor_top_n_comprehensive
        if coverage_mode == "comprehensive"
        else s.competitor_top_n_standard
    )
    try:
        result = run_refinement_pipeline(
            seed=seed,
            topics=[
                PipelineTopic(
                    id=t["id"],
                    name=t["name"],
                    embedding=embeddings.get(t["id"]),
                    gated=bool(t.get("is_gated_for_competitor_mining")),
                )
                for t in topics
            ],
            dfs=get_dataforseo(),
            embed_fn=get_llm().embed,
            keyword_ideas_limit=s.keyword_ideas_limit,
            keyword_suggestions_limit=s.keyword_suggestions_limit,
            query_fanouts_limit=s.query_fanouts_limit,
            paa_tier1_seeds=s.paa_tier1_seeds,
            paa_tier2_cap=s.paa_tier2_cap,
            autocomplete_max=s.autocomplete_max,
            expansion_max_workers=s.expansion_max_workers,
            expansion_time_budget_s=s.expansion_time_budget_s,
            competitor_top_n=top_n,
            ranked_keywords_limit=s.ranked_keywords_limit,
            competitor_max_position=s.competitor_max_position,
            competitor_max_workers=s.competitor_max_workers,
            competitor_time_budget_s=s.competitor_time_budget_s,
            relevance_threshold=s.relevance_threshold,
            relevance_embed_batch=s.relevance_embed_batch,
            clustering_edge_threshold=s.clustering_edge_threshold,
        )
        store.delete_keywords_for_session(session_id)
        count = store.insert_classified_keywords(session_id, result.per_topic_gated)
        store.update_session(
            session_id, {"statistical_clustering_log": result.clustering_log}
        )
    except Exception as exc:
        store.update_session(session_id, {"status": "error"})
        logger.error(
            "step_failed",
            extra={"event": "step_failed", "step": "refinement_pipeline",
                   "reason": repr(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The keyword pipeline failed. The session was marked as errored; try again.",
        ) from exc

    # M4 is the current pipeline terminus; M5 (orchestrator) moves this downstream.
    store.update_session(session_id, {"status": "complete"})

    counts = result.counts()
    names = {t["id"]: t["name"] for t in topics}
    groupings = result.clustering_log.get("topics", {})
    return {
        "expanded": True,
        "keyword_count": count,
        "counts": counts,
        "degraded_notes": result.degraded_notes,
        "timed_out": result.timed_out,
        "topics": [
            {
                "topic_id": tid,
                "name": names.get(tid, ""),
                "active": sum(1 for g in kws if g.status == "active"),
                "total": len(kws),
                "grouping_count": groupings.get(tid, {}).get("grouping_count", 0),
            }
            for tid, kws in result.per_topic_gated.items()
        ],
    }


@router.get("/sessions/{session_id}/keywords")
def get_keywords(
    session_id: str,
    user: AuthedUser = Depends(require_user),
    topic_id: str | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    _require_session(user, session_id)
    return store.list_keywords(
        session_id, topic_id=topic_id, status=status, limit=min(limit, 500), offset=offset
    )


# ---- Topic review actions (PRD §7.1.4) ------------------------------------
@router.post("/sessions/{session_id}/topics")
def add_topic(
    session_id: str, body: AddTopicBody, user: AuthedUser = Depends(require_user)
) -> dict:
    _require_session(user, session_id)
    bind_session_id(session_id)
    return store.insert_custom_topic(
        session_id,
        name=body.name.strip(),
        rationale=body.rationale,
        relationship_type=body.relationship_type.value,
        is_broader_class=body.is_broader_class
        or body.relationship_type is RelationshipType.broader_class,
    )


@router.patch("/topics/{topic_id}")
def edit_topic(
    topic_id: str, body: EditTopicBody, user: AuthedUser = Depends(require_user)
) -> dict:
    topic = store.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    _require_session(user, topic["session_id"])
    bind_session_id(topic["session_id"])

    fields: dict = {}
    if body.name is not None:
        fields["name"] = body.name.strip()
    if body.rationale is not None:
        fields["rationale"] = body.rationale
    if body.relationship_type is not None:
        fields["relationship_type"] = body.relationship_type.value
        fields["is_broader_class"] = body.relationship_type is RelationshipType.broader_class
    if not fields:
        return topic

    # An edited LLM silo is retagged so provenance is traceable (PRD §13).
    if topic["source"] == "llm_proposed":
        fields["source"] = "llm_proposed_then_user_edited"
    return store.update_topic(topic_id, fields)


@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_topic(topic_id: str, user: AuthedUser = Depends(require_user)) -> None:
    topic = store.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    _require_session(user, topic["session_id"])
    bind_session_id(topic["session_id"])
    store.delete_topic(topic_id)


# Re-export for callers that validate relationship types.
__all__ = ["router", "PROPOSABLE_TYPES"]
