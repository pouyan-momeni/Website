"""FastAPI authentication dependencies."""

from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.jwt import TokenError, decode_token
from backend.config import settings
from backend.database import get_db
from backend.models.user import User


# Async Redis client for token blacklist
_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Get or create the async Redis connection."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract and validate the JWT access token from the Authorization header.
    Returns the authenticated User ORM object.

    In develop mode with dev bypass users, returns a synthetic User object
    without requiring DB or Redis.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1]

    try:
        payload = decode_token(token, expected_type="access")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    user_id = payload.get("sub")
    username = payload.get("username")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # ── Dev-mode bypass: return synthetic user without DB/Redis ──
    from backend.config import DEV_USERS
    if settings.is_develop and username in DEV_USERS:
        import types
        dev_info = DEV_USERS[username]
        return types.SimpleNamespace(
            id=UUID(dev_info["id"]),
            ldap_username=username,
            email=dev_info["email"],
            role=dev_info["role"],
            is_active=True,
        )

    # ── Production path: verify against DB and Redis ──
    # Check token blacklist
    redis_client = await get_redis()
    if await redis_client.get(f"blacklist:{token}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    return user


def require_role(allowed_roles: list[str]):
    """
    FastAPI dependency factory that checks the user's role against allowed roles.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_role(["admin"]))])
    """
    async def _check_role(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' not authorized. Required: {allowed_roles}",
            )
        return current_user

    return _check_role


def require_develop_mode():
    """
    FastAPI dependency that returns 403 if APP_MODE != 'develop'.
    Ensures develop-only features are blocked in production regardless of role.
    """
    async def _check_mode() -> None:
        if not settings.is_develop:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This feature is only available in develop mode",
            )

    return _check_mode
