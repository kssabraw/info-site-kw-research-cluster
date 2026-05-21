"""Silo-discovery endpoints (M2).

Lifecycle: create a session (runs grounding + proposal), optionally resolve a
disambiguation choice, review/edit the proposed silos, then finalize — which
embeds each silo and halts (expansion is M3).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import AuthedUser, require_user
from app.dataforseo import get_dataforseo
from app.llm import LLMError, get_llm
from app.logging import bind_session_id
from app.pipeline.models import PROPOSABLE_TYPES, RelationshipType
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
        )
    except LLMError as exc:
        store.update_session(session["id"], {"status": "error"})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Silo discovery could not complete (grounding unavailable). Try again.",
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


# ---- Topic review actions (PRD §7.1.4) ------------------------------------
@router.post("/sessions/{session_id}/topics")
def add_topic(
    session_id: str, body: AddTopicBody, user: AuthedUser = Depends(require_user)
) -> dict:
    _require_session(user, session_id)
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
    store.delete_topic(topic_id)


# Re-export for callers that validate relationship types.
__all__ = ["router", "PROPOSABLE_TYPES"]
