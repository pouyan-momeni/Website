"""Monitoring API routes: resources, containers, and notebooks."""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth.dependencies import require_role
from backend.config import settings
from backend.docker_runner.runner import DockerRunner
from backend.models.user import User
from backend.schemas.schemas import ResourceSnapshot, ContainerInfo, NotebookMonitorInfo
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
                    cpu_percent=round((hash(str(run.id)) % 50) + 5, 1),
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
            cpu_percent=c.cpu_percent,
        )
        for c in containers
    ]


@router.get("/notebooks", response_model=list[NotebookMonitorInfo])
async def get_notebooks(
    current_user: User = Depends(require_role(["admin", "developer", "runner"])),
):
    """List running notebooks with resource stats. Runner+ role required."""
    from backend.api.notebooks import _NOTEBOOKS

    running = [nb for nb in _NOTEBOOKS.values() if nb.get("status") == "running"]
    results = []
    for nb in running:
        cpu_percent = None
        memory_mb = None

        # In production, try to get real stats if docker_id is available
        if not settings.is_develop and nb.get("docker_id"):
            try:
                runner = DockerRunner()
                stats = runner.get_container_stats(nb["docker_id"])
                cpu_percent = stats.get("cpu_percent")
                memory_mb = stats.get("memory_mb")
            except Exception:
                pass

        # Dev mode: simulate stats with random fluctuation
        if settings.is_develop:
            import random
            base_cpu = (hash(nb["id"]) % 20) + 5
            base_mem = 80 + (hash(nb["id"]) % 100)
            cpu_percent = round(base_cpu + random.uniform(-3, 5), 1)
            memory_mb = round(base_mem + random.uniform(-10, 15), 1)

        results.append(NotebookMonitorInfo(
            id=nb["id"],
            name=nb["name"],
            owner_username=nb.get("owner_username", "unknown"),
            status=nb["status"],
            url=nb.get("url"),
            port=nb.get("port"),
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            started_at=nb.get("updated_at"),
        ))

    return results


@router.delete("/containers/{docker_id}")
async def kill_container(
    docker_id: str,
    current_user: User = Depends(require_role(["admin"])),
):
    """Kill a running Docker container immediately. Admin only."""
    runner = DockerRunner()
    try:
        runner.kill_container(docker_id)
        return {"detail": f"Container {docker_id} killed"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to kill container: {exc}",
        )


@router.post("/containers/{docker_id}/pause")
async def pause_container(
    docker_id: str,
    current_user: User = Depends(require_role(["admin"])),
):
    """Pause a running container. Admin only."""
    runner = DockerRunner()
    try:
        runner.pause_container(docker_id)
        return {"detail": f"Container {docker_id} paused"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause container: {exc}",
        )


@router.post("/containers/{docker_id}/resume")
async def resume_container(
    docker_id: str,
    current_user: User = Depends(require_role(["admin"])),
):
    """Resume a paused container. Admin only."""
    runner = DockerRunner()
    try:
        runner.resume_container(docker_id)
        return {"detail": f"Container {docker_id} resumed"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume container: {exc}",
        )


@router.post("/notebooks/{notebook_id}/stop")
async def stop_notebook_from_monitoring(
    notebook_id: str,
    current_user: User = Depends(require_role(["admin"])),
):
    """Stop a running notebook. Admin only."""
    from backend.api.notebooks import _NOTEBOOKS

    nb = _NOTEBOOKS.get(notebook_id)
    if not nb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    if nb["status"] == "stopped":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already stopped")

    nb["status"] = "stopped"
    nb["port"] = None
    nb["url"] = None

    from datetime import datetime, timezone
    nb["updated_at"] = datetime.now(timezone.utc).isoformat()

    return {"detail": f"Notebook '{nb['name']}' stopped"}
