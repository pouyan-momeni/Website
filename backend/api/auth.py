"""Auth API routes: login, refresh, logout."""

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user, get_redis
from backend.auth.jwt import create_access_token, create_refresh_token, decode_token, TokenError
from backend.auth.ldap import authenticate_ldap, InvalidCredentialsError
from backend.config import settings, DEV_USERS
from backend.database import get_db
from backend.models.user import User
from backend.schemas.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate via LDAP (or dev bypass), return JWT access token, set refresh token cookie."""

    # ── Dev-mode bypass: authenticate against hardcoded users ──
    if settings.is_develop and body.username in DEV_USERS:
        dev_user = DEV_USERS[body.username]
        if body.password != dev_user["password"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        from uuid import UUID
        user_id = UUID(dev_user["id"])
        access_token = create_access_token(user_id, body.username, dev_user["role"])
        refresh_token = create_refresh_token(user_id, body.username)

        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
            path="/api/auth",
        )

        from backend.api.audit import log_action
        log_action(body.username, dev_user["id"], "login", "auth", details={"role": dev_user["role"]})

        return TokenResponse(access_token=access_token)

    # ── Production path: LDAP authentication ──
    try:
        ldap_info = authenticate_ldap(body.username, body.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Find or create user record
    result = await db.execute(
        select(User).where(User.ldap_username == ldap_info["ldap_username"])
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account not provisioned. Contact an administrator.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    # Update email if changed in LDAP
    if ldap_info["email"] and ldap_info["email"] != user.email:
        user.email = ldap_info["email"]

    # Create tokens
    access_token = create_access_token(user.id, user.ldap_username, user.role)
    refresh_token = create_refresh_token(user.id, user.ldap_username)

    # Set refresh token as httpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
        path="/api/auth",
    )

    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Validate refresh token from cookie, return new access token."""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided",
        )

    # Check token blacklist
    redis_client = await get_redis()
    if await redis_client.get(f"blacklist:{refresh_token}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )

    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    # Issue new access token
    access_token = create_access_token(user.id, user.ldap_username, user.role)

    return TokenResponse(access_token=access_token)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    authorization: str = "",
    current_user: User = Depends(get_current_user),
):
    """Blacklist the current access token and clear refresh cookie."""
    redis_client = await get_redis()

    # Blacklist the access token
    if authorization and authorization.startswith("Bearer "):
        access_token = authorization.split(" ", 1)[1]
        await redis_client.setex(
            f"blacklist:{access_token}",
            settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "1",
        )

    # Blacklist the refresh token
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        await redis_client.setex(
            f"blacklist:{refresh_token}",
            settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
            "1",
        )

    # Clear the cookie
    response.delete_cookie("refresh_token", path="/api/auth")

    return {"detail": "Logged out successfully"}
