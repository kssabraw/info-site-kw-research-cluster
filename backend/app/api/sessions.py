"""Session endpoints: silo discovery (M2) + keyword pipeline (M3/M4).

Lifecycle: create a session (grounding + proposal), optionally resolve
disambiguation, review/edit silos, finalize (embeds each silo), pick which silos
to deep-mine (§7.2), then run /expand — which now runs the full refinement
pipeline: expansion + competitor mining + relevance gate + statistical clustering.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app import jobs
from app.auth import AuthedUser, require_user
from app.config import get_settings
from app.dataforseo import get_dataforseo
from app.llm import LLMError, get_llm
from app.logging import bind_session_id
from app.pipeline.models import PROPOSABLE_TYPES, RelationshipType
from app.pipeline.orchestrate import cluster_preview
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


class RegateBody(BaseModel):
    # Optional per-call overrides so threshold + clustering granularity can be
    # tuned without changing the Railway env. Omitted values fall back to config.
    relevance_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    clustering_edge_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    clustering_resolution: float | None = Field(default=None, gt=0.0, le=20.0)


class ClusterPreviewBody(BaseModel):
    # Granularity sweep: gate once, then report cluster stats for each
    # (edge_threshold, resolution) config. Read-only — nothing is persisted.
    relevance_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    configs: list[tuple[float, float]] = Field(
        default_factory=lambda: [(0.55, 1.0), (0.7, 1.0), (0.75, 1.5), (0.8, 2.0)],
        max_length=12,
    )


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
@router.post("/sessions/{session_id}/expand", status_code=status.HTTP_202_ACCEPTED)
def expand_session(session_id: str, user: AuthedUser = Depends(require_user)) -> dict:
    """Kick off the §7.3–§7.9 pipeline in the background and return immediately.
    The work runs past the 5-min edge cap, so the frontend polls
    GET /sessions/{id}/summary for status. The atomic run guard rejects a
    double-submit (409)."""
    _require_session(user, session_id)
    bind_session_id(session_id)
    if not store.list_topics(session_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No silos to expand. Finalize at least one silo first.",
        )
    if not store.try_mark_running(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pipeline run is already in progress for this session.",
        )
    jobs.submit_expand(session_id)
    return {"status": "running", "session_id": session_id}


@router.get("/sessions/{session_id}/summary")
def session_summary(session_id: str, user: AuthedUser = Depends(require_user)) -> dict:
    """Status + expansion/plan counts. Polled by the frontend to drive the UI and
    to resume a session on refresh; `plan` is null until the orchestrator runs."""
    _require_session(user, session_id)
    return store.get_pipeline_summary(session_id)


@router.post("/sessions/{session_id}/regate", status_code=status.HTTP_202_ACCEPTED)
def regate_session(
    session_id: str, body: RegateBody, user: AuthedUser = Depends(require_user)
) -> dict:
    """Kick off a re-gate (relevance gate + clustering) on the session's stored
    keyword pool at a (possibly overridden) threshold in the background, skipping
    DataForSEO. Returns immediately; poll GET /summary for status. A calibration
    tool: tune the threshold without re-paying for expansion + mining."""
    _require_session(user, session_id)
    bind_session_id(session_id)
    if not store.list_all_keyword_pool(session_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No keywords to re-gate. Run /expand first.",
        )
    if not store.try_mark_running(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A run is already in progress for this session.",
        )
    s = get_settings()
    threshold = (
        body.relevance_threshold
        if body.relevance_threshold is not None
        else s.relevance_threshold
    )
    edge = (
        body.clustering_edge_threshold
        if body.clustering_edge_threshold is not None
        else s.clustering_edge_threshold
    )
    resolution = (
        body.clustering_resolution
        if body.clustering_resolution is not None
        else s.clustering_resolution
    )
    jobs.submit_regate(session_id, threshold, edge, resolution)
    return {
        "status": "running",
        "session_id": session_id,
        "relevance_threshold": threshold,
        "clustering_edge_threshold": edge,
        "clustering_resolution": resolution,
    }


@router.post("/sessions/{session_id}/cluster-preview")
def cluster_preview_endpoint(
    session_id: str, body: ClusterPreviewBody, user: AuthedUser = Depends(require_user)
) -> dict:
    """Granularity sweep (read-only): embed + gate the stored keyword pool once,
    then report cluster-size stats for each (edge_threshold, resolution) config.
    Synchronous (no persistence, no status change) — it's a quick analysis call
    used to pick clustering settings before committing a /regate."""
    _require_session(user, session_id)
    bind_session_id(session_id)
    pool = store.list_all_keyword_pool(session_id)
    if not pool:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No keywords to preview. Run /expand first.",
        )
    s = get_settings()
    threshold = (
        body.relevance_threshold
        if body.relevance_threshold is not None
        else s.relevance_threshold
    )
    topics = store.list_topics(session_id)
    return cluster_preview(
        per_topic_lists=pool,
        topic_names={t["id"]: t["name"] for t in topics},
        topic_embeddings=store.get_topic_embeddings(session_id),
        embed_fn=get_llm().embed,
        relevance_threshold=threshold,
        configs=[(float(e), float(r)) for e, r in body.configs],
        relevance_embed_batch=s.relevance_embed_batch,
        clustering_max_nodes=s.clustering_max_nodes,
    )


@router.post("/sessions/{session_id}/plan-articles", status_code=status.HTTP_202_ACCEPTED)
def plan_articles(session_id: str, user: AuthedUser = Depends(require_user)) -> dict:
    """Kick off M5 article planning (§7.10) in the background: SERP for candidate
    primaries -> per-silo orchestrator -> cross-topic dedup -> persist clusters +
    coverage gaps. Returns immediately; poll GET /summary for status."""
    session = _require_session(user, session_id)
    bind_session_id(session_id)
    if not (session.get("statistical_clustering_log") or {}).get("topics"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No statistical clustering to plan from. Run /expand first.",
        )
    if not store.try_mark_running(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A run is already in progress for this session.",
        )
    jobs.submit_plan(session_id)
    return {"status": "running", "session_id": session_id}


@router.get("/sessions/{session_id}/clusters")
def get_clusters(session_id: str, user: AuthedUser = Depends(require_user)) -> dict:
    """Read-only article plan + coverage gaps for a session (M5 verification /
    minimal UI; full editing views are M7)."""
    _require_session(user, session_id)
    return {
        "clusters": store.list_clusters(session_id),
        "coverage_gaps": store.list_coverage_gaps(session_id),
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
