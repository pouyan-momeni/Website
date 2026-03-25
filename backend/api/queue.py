"""Queue API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import require_role
from backend.config import settings
from backend.database import get_db
from backend.models.user import User
from backend.schemas.schemas import QueueReorderRequest, RunListResponse
from backend.services import queue_service

router = APIRouter(prefix="/api/queue", tags=["queue"])


@router.get("")
async def get_queue(
    current_user: User = Depends(require_role(["admin", "developer", "runner"])),
    db: AsyncSession = Depends(get_db),
):
    """Get the current run queue (queued + running). Runner+ role required."""
    if settings.is_develop:
        from backend.api.runs import _DEV_RUNS, _get_model_name
        active_runs = [
            r for r in _DEV_RUNS.values()
            if r["status"] in ("queued", "running")
        ]
        # Enrich
        for r in active_runs:
            r["model_name"] = _get_model_name(r["model_id"])
            r["username"] = "admin"
        # Sort: running first, then queued by position
        active_runs.sort(key=lambda r: (
            0 if r["status"] == "running" else 1,
            r.get("queue_position", 999),
        ))
        return active_runs

    runs = await queue_service.get_queue(db)
    response = []
    
    from backend.models.model import Model
    from sqlalchemy import select
    
    for run in runs:
        run_data = RunListResponse.model_validate(run)
        
        # Populate model_name
        model_result = await db.execute(select(Model.name).where(Model.id == run.model_id))
        run_data.model_name = model_result.scalar_one_or_none()
        
        # Populate username
        user_result = await db.execute(select(User.ldap_username).where(User.id == run.triggered_by))
        run_data.username = user_result.scalar_one_or_none()
        
        response.append(run_data)
        
    return response


@router.put("/reorder")
async def reorder_queue(
    body: QueueReorderRequest,
    current_user: User = Depends(require_role(["admin", "developer", "runner"])),
    db: AsyncSession = Depends(get_db),
):
    """Reorder queued runs. Only affects waiting runs. Runner+ role required."""
    if settings.is_develop:
        from backend.api.runs import _DEV_RUNS
        for idx, run_id in enumerate(body.run_ids):
            run = _DEV_RUNS.get(str(run_id))
            if run and run["status"] == "queued":
                run["queue_position"] = idx + 1
        return {"detail": "Queue reordered successfully"}

    await queue_service.reorder_queue(db, body.run_ids)
    return {"detail": "Queue reordered successfully"}
