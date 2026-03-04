"""Monitoring API routes: resources and containers."""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth.dependencies import require_role
from backend.config import settings
from backend.docker_runner.runner import DockerRunner
from backend.models.user import User
from backend.schemas.schemas import ResourceSnapshot, ContainerInfo
from backend.services import resource_service

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/resources", response_model=ResourceSnapshot)
async def get_resources(
    current_user: User = Depends(require_role(["admin", "developer", "runner"])),
):
    """Get current system resource snapshot. Runner+ role required."""
    return resource_service.get_snapshot()


@router.get("/containers", response_model=list[ContainerInfo])
async def get_containers(
    current_user: User = Depends(require_role(["admin", "developer", "runner"])),
):
    """List running Docker containers managed by this app. Runner+ role required."""
    # Dev mode: simulate containers from running DB runs
    if settings.is_develop:
        from sqlalchemy import select, create_engine
        from sqlalchemy.orm import Session, sessionmaker
        from backend.models.run import Run
        from backend.models.model import Model

        sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        SyncSessionLocal = sessionmaker(bind=sync_engine)
        db = SyncSessionLocal()
        try:
            running_runs = db.execute(
                select(Run).where(Run.status == "running")
            ).scalars().all()

            containers = []
            for run in running_runs:
                model = db.execute(select(Model).where(Model.id == run.model_id)).scalar_one_or_none()
                model_name = model.name if model else "Unknown"
                container_names = ["data-updater", "analyze", "backtest"]
                idx = min(run.current_container_index or 0, len(container_names) - 1)
                containers.append(ContainerInfo(
                    docker_id=str(run.id)[:12],
                    name=f"almplatform-{str(run.id)[:8]}-{container_names[idx]}",
                    image=f"alm/{container_names[idx]}:latest",
                    status="running",
                    run_id=str(run.id),
                    started_at=run.started_at.isoformat() if run.started_at else None,
                    memory_usage_mb=round(128 + hash(str(run.id)) % 256, 2),
                ))
            return containers
        finally:
            db.close()

    runner = DockerRunner()
    containers = runner.list_running_containers()
    return [
        ContainerInfo(
            docker_id=c.docker_id,
            name=c.name,
            image=c.image,
            status=c.status,
            run_id=c.run_id,
            started_at=c.started_at,
            memory_usage_mb=c.memory_usage_mb,
        )
        for c in containers
    ]


@router.delete("/containers/{docker_id}")
async def kill_container(
    docker_id: str,
    current_user: User = Depends(require_role(["admin", "developer", "runner"])),
):
    """Kill a running Docker container immediately. Runner+ role required."""
    runner = DockerRunner()
    try:
        runner.kill_container(docker_id)
        return {"detail": f"Container {docker_id} killed"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to kill container: {exc}",
        )
