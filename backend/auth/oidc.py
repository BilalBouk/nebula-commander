"""
OIDC authentication middleware. Validates JWT from OIDC provider (Authelia, Authentik, etc.)
or from our own JWT secret. When oidc_issuer_url is set, JWTs are validated using the
provider's JWKS; otherwise the configured JWT secret is used.
Also: device tokens (JWT with sub=device, node_id, ver) for dnclient-style enrollment.
"""
import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt
from pydantic import BaseModel

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..models.db import Node

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

# Cache for JWKS (issuer URL -> {"keys": [...]})
_jwks_cache: dict[str, dict] = {}
_jwks_cache_issuer: Optional[str] = None


def _fetch_jwks(issuer_url: str) -> dict:
    """Fetch JWKS from OIDC issuer. Caches result."""
    global _jwks_cache_issuer, _jwks_cache
    base = issuer_url.rstrip("/")
    jwks_url = f"{base}/.well-known/jwks.json"
    if _jwks_cache_issuer != jwks_url:
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(jwks_url)
                r.raise_for_status()
                _jwks_cache = r.json()
                _jwks_cache_issuer = jwks_url
        except Exception as e:
            logger.warning("Failed to fetch JWKS from %s: %s", jwks_url, e)
            _jwks_cache = {}
    return _jwks_cache


def _get_signing_key_from_jwks(token: str, issuer_url: str) -> Optional[dict]:
    """Get the signing key for the token from JWKS."""
    try:
        unverified = jwt.get_unverified_header(token)
        kid = unverified.get("kid")
        if not kid:
            return None
        jwks = _fetch_jwks(issuer_url)
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key
        return None
    except Exception:
        return None


def _accepted_oidc_issuers() -> tuple[str, ...]:
    """Issuer values accepted on provider (RS256) tokens.

    The backend may fetch JWKS over an internal URL (http://keycloak:8080/...) while
    browser-issued tokens carry the PUBLIC issuer URL, so both configured URLs are
    accepted, each with and without a trailing slash (jose compares iss exactly).
    """
    issuers: list[str] = []
    for url in (settings.oidc_public_issuer_url, settings.oidc_issuer_url):
        if url:
            issuers.extend((url, url.rstrip("/")))
    return tuple(dict.fromkeys(issuers))


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT.

    When OIDC is configured a token is accepted only if it is either RS-signed by the
    provider (validated against its JWKS, with audience AND issuer pinned to the
    configured provider URLs) OR one of OUR own locally-minted HS256 tokens, identified
    by iss == local_jwt_issuer. We deliberately do NOT fall back to accepting an
    arbitrary HS256 token as an OIDC identity: without the issuer marker the
    local-secret path would let anyone who knows the symmetric secret forge a provider user
    (security audit C1). Local tokens carry our issuer claim, enforced on the HS256 branch.
    """
    try:
        if settings.oidc_issuer_url:
            # Prefer OIDC JWKS validation (tokens minted by Keycloak/etc.)
            key_data = _get_signing_key_from_jwks(token, settings.oidc_issuer_url)
            if key_data:
                return jwt.decode(
                    token,
                    jwk.construct(key_data),
                    algorithms=["RS256", "RS384", "RS512"],
                    audience=settings.oidc_client_id,
                    issuer=_accepted_oidc_issuers(),
                    options={"verify_aud": bool(settings.oidc_client_id)},
                )
            # Not IdP-signed: the only other thing we accept is our own locally-minted
            # token, which must be stamped with our issuer (enforced just below).
        
        # Validate using local JWT secret; require our issuer claim so a forged token
        # cannot masquerade as an OIDC identity or a different token type.
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.local_jwt_issuer,
        )
        # Only user-session tokens are valid here. Device tokens (sub=device) and reauth
        # tokens (reauth=True) are signed with the same secret+issuer but MUST NOT be
        # accepted as a user session — they have their own decoders. Without this check a
        # device/reauth token replays as a full authenticated user (security audit).
        if payload.get("typ") != "session":
            return None
        return payload
    except JWTError:
        return None


class UserInfo(BaseModel):
    """User info from OIDC token."""

    sub: str
    email: Optional[str] = None
    role: str = "user"  # Legacy field
    system_role: str = "user"  # system-admin or user; network ownership is per-network in backend


async def get_current_user_optional(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(security)
    ] = None,
) -> Optional[UserInfo]:
    """
    Dependency: optional current user from Bearer token.
    Returns None if no token or invalid token.
    """
    if not credentials or not credentials.credentials:
        return None
    payload = decode_token(credentials.credentials)
    if not payload:
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    return UserInfo(
        sub=sub,
        email=payload.get("email"),
        role=payload.get("role", "user"),
        system_role=payload.get("system_role", payload.get("role", "user")),
    )


async def require_user(
    user: Annotated[Optional[UserInfo], Depends(get_current_user_optional)] = None,
) -> UserInfo:
    """Dependency: require authenticated user. Raises 401 if not logged in."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# --- Device token (for dnclient-style enrollment) ---

def create_device_token(node_id: int, version: int) -> str:
    """Create a long-lived JWT for a device (node).

    Payload: sub=device, node_id=N, ver=version
    """
    exp = datetime.utcnow() + timedelta(days=settings.device_token_expiration_days)
    payload = {
        "sub": "device",
        "node_id": node_id,
        "ver": version,
        "exp": exp,
        "iss": settings.local_jwt_issuer,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_device_token(token: str) -> Optional[tuple[int, int]]:
    """Decode device JWT; return (node_id, version) or None."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.local_jwt_issuer,
        )
        if payload.get("sub") != "device":
            return None
        node_id = payload.get("node_id")
        if node_id is None:
            return None
        # Tokens issued before versioning did not include \"ver\"; treat them as version 1.
        version = payload.get("ver", 1)
        return int(node_id), int(version)
    except JWTError:
        return None


async def require_device_token(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(security)
    ] = None,
    session: AsyncSession = Depends(get_session),
) -> int:
    """Dependency: require device Bearer token; return node_id. Raises 401 if invalid.

    In addition to validating the JWT, this enforces per-node token versioning so that
    older tokens are invalidated when a new token is issued for the node.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid device token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    decoded = decode_device_token(credentials.credentials)
    if decoded is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired device token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    node_id, token_version = decoded

    # Enforce that the token version matches the current version stored on the node.
    result = await session.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node or (node.device_token_version or 1) != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired device token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return node_id
