"""Marimo notebook API routes — develop mode only."""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth.dependencies import require_role, require_develop_mode
from backend.models.user import User
from backend.schemas.schemas import MarimoLaunchResponse, MarimoStatusResponse
from backend.services.marimo_service import marimo_service
from backend.config import settings

router = APIRouter(prefix="/api/marimo", tags=["marimo"])


@router.post("/launch", response_model=MarimoLaunchResponse)
async def launch_marimo(
    current_user: User = Depends(require_role(["admin", "developer"])),
    _: None = Depends(require_develop_mode()),
):
    """Launch a Marimo notebook instance for the current user. Developer+ only, develop mode only."""
    try:
        port = marimo_service.launch_for_user(current_user.ldap_username)
        url = f"/marimo/{current_user.ldap_username}/"
        return MarimoLaunchResponse(port=port, url=url)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )


@router.get("/status", response_model=MarimoStatusResponse)
async def get_marimo_status(
    current_user: User = Depends(require_role(["admin", "developer"])),
    _: None = Depends(require_develop_mode()),
):
    """Get the status of the current user's Marimo instance. Developer+ only, develop mode only."""
    status_info = marimo_service.get_status(current_user.ldap_username)
    if status_info["running"]:
        return MarimoStatusResponse(
            running=True,
            port=status_info["port"],
            url=f"/marimo/{current_user.ldap_username}/",
        )
    return MarimoStatusResponse(running=False)
