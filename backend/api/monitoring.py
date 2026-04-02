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
    # Dev mode: derive containers from in-memory active runs (DB is not used in dev mode)
    if settings.is_develop:
        import random
        from backend.api.runs import _DEV_RUNS, _ACTIVE_RUN_IDS

        from backend.api.runs import _get_model_docker_images
        containers = []
        for run_id in list(_ACTIVE_RUN_IDS):
            run = _DEV_RUNS.get(run_id)
            if not run or run.get("status") != "running":
                continue
            docker_images = _get_model_docker_images(run["model_id"])
            idx = run.get("current_container_index") or 0
            if docker_images and idx < len(docker_images):
                img_spec = docker_images[idx]
                container_name = img_spec.get("name", f"container-{idx}")
                image = img_spec.get("image", f"alm/unknown:latest")
            else:
                container_names = ["data-updater", "analyze", "backtest"]
                container_name = container_names[min(idx, len(container_names) - 1)]
                image = f"alm/{container_name}:latest"
            rng_seed = hash(run_id + container_name)
            containers.append(ContainerInfo(
                docker_id=run_id[:12],
                name=f"almplatform-{run_id[:8]}-{container_name}",
                image=image,
                status="running",
                run_id=run_id,
                started_at=run.get("started_at"),
                memory_usage_mb=round(128 + (rng_seed % 256) + random.uniform(-10, 10), 1),
                cpu_percent=round(5 + (rng_seed % 50) + random.uniform(-3, 5), 1),
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
