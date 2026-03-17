"""Users API routes: admin user management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import require_role
from backend.database import get_db
from backend.models.user import User
from backend.schemas.schemas import UserCreate, UserUpdate, UserResponse

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """List all users. Admin only."""
    result = await db.execute(select(User).order_by(User.ldap_username))
    return result.scalars().all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Create a user record with role assignment. Admin only."""
    # Check uniqueness
    existing = await db.execute(
        select(User).where(User.ldap_username == body.ldap_username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User '{body.ldap_username}' already exists",
        )

    user = User(
        ldap_username=body.ldap_username,
        email=body.email,
        role=body.role,
    )
    db.add(user)
    await db.flush()

    # Create personal notebook folder for the new user
    import os
    from backend.config import settings as app_settings
    user_folder = os.path.join(app_settings.MARIMO_BASE_PATH, body.ldap_username)
    os.makedirs(user_folder, exist_ok=True)

    # Audit log the creation
    from backend.api.audit import log_action
    await log_action(
        username=current_user.ldap_username,
        user_id=str(current_user.id),
        action="create_user",
        resource_type="user",
        resource_id=str(user.id),
        details={"created_username": body.ldap_username, "role": body.role, "notebook_folder": user_folder},
        db=db,
    )

    return user


@router.put("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: UUID,
    body: UserUpdate,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's role. Admin only."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.role = body.role
    await db.flush()
    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: UUID,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a user. Admin only."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    deleted_username = user.ldap_username
    await db.delete(user)
    await db.flush()

    # Audit log the deletion
    from backend.api.audit import log_action
    await log_action(
        username=current_user.ldap_username,
        user_id=str(current_user.id),
        action="delete_user",
        resource_type="user",
        resource_id=str(user_id),
        details={"deleted_username": deleted_username},
        db=db,
    )

    return {"detail": f"User '{deleted_username}' deleted"}
