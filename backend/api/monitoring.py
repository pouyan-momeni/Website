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
    # Dev mode: simulate containers from running dev runs
    if settings.is_develop:
        from backend.api.runs import _DEV_RUNS, _get_model_name
        containers = []
        for run_id, run in _DEV_RUNS.items():
            if run["status"] == "running":
                model_name = _get_model_name(run["model_id"])
                container_names = ["data-updater", "analyze", "backtest"]
                idx = min(run.get("current_container_index", 0), len(container_names) - 1)
                containers.append(ContainerInfo(
                    docker_id=run_id[:12],
                    name=f"almplatform-{run_id[:8]}-{container_names[idx]}",
                    image=f"alm/{container_names[idx]}:latest",
                    status="running",
                    run_id=run_id,
                    started_at=run.get("started_at"),
                    memory_usage_mb=round(128 + hash(run_id) % 256, 2),
                ))
        return containers

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
