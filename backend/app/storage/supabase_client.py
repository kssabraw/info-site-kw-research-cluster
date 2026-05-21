"""Supabase client wrappers.

Two access paths (PRD §13: "the FastAPI service uses the user's JWT to drive the
policy"):

- service client  — built with the service-role key, bypasses RLS. Used for
  admin writes the backend fully controls (provisioning a profile, the Scratch
  project).
- user client     — built with the anon key plus the caller's JWT in the
  Authorization header, so PostgREST enforces RLS as that user. Used for all
  scoped reads.

Both default to the `fanout` schema, which must be added to the project's
PostgREST "Exposed schemas" (Supabase dashboard → API settings).
"""

from functools import lru_cache

from supabase import Client, create_client
from supabase.lib.client_options import ClientOptions

from app.config import get_settings


@lru_cache
def get_service_client() -> Client:
    settings = get_settings()
    options = ClientOptions(schema=settings.fanout_schema)
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options,
    )


def get_user_client(access_token: str) -> Client:
    settings = get_settings()
    options = ClientOptions(
        schema=settings.fanout_schema,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return create_client(settings.supabase_url, settings.supabase_anon_key, options)


def ensure_user_profile(user_id: str, email: str | None) -> dict:
    """Return the caller's profile row, creating a default `va` profile on first
    login. The Owner (Kyle) is seeded by the M1 migration; everyone else defaults
    to `va` until an Owner promotes them.
    """
    service = get_service_client()
    existing = (
        service.table("user_profiles")
        .select("user_id, display_name, role")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]

    display_name = (email or "").split("@")[0] or None
    inserted = (
        service.table("user_profiles")
        .insert({"user_id": user_id, "display_name": display_name, "role": "va"})
        .execute()
    )
    return inserted.data[0]


def ensure_scratch_project(user_id: str) -> dict:
    """Return the caller's Scratch project, auto-creating it on first login
    (PRD §15.1, §9.4)."""
    service = get_service_client()
    existing = (
        service.table("projects")
        .select("id, name, is_scratch, created_at")
        .eq("user_id", user_id)
        .eq("is_scratch", True)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]

    inserted = (
        service.table("projects")
        .insert({"user_id": user_id, "name": "Scratch", "is_scratch": True})
        .execute()
    )
    return inserted.data[0]
