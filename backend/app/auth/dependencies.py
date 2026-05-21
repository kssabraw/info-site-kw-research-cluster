"""Auth dependency: verify the Supabase JWT and expose the caller.

The bearer token is validated against Supabase Auth (which checks the
signature/expiry). The raw token is retained on the returned object so scoped
queries can run as the user with RLS enforced.
"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.storage import get_service_client

_bearer = HTTPBearer(auto_error=True)


@dataclass
class AuthedUser:
    id: str
    email: str | None
    access_token: str


def require_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> AuthedUser:
    token = creds.credentials
    try:
        result = get_service_client().auth.get_user(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = getattr(result, "user", None)
    if user is None or not user.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return AuthedUser(id=user.id, email=user.email, access_token=token)
