from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict:
    """Liveness probe. Used by Railway's healthcheck (PRD §15.1)."""
    return {"status": "ok", "service": "info-site-kw-research-cluster"}
