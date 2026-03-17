"""Docker container runner using docker-py SDK."""

import logging
import shlex
from dataclasses import dataclass, field
from typing import Optional

import docker
import redis

from backend.config import settings

logger = logging.getLogger(__name__)


class ImageNotFoundError(Exception):
    """Raised when a requested Docker image is not available locally."""
    pass


@dataclass
class ContainerResult:
    """Result of a container execution."""
    exit_code: int
    log: str
    docker_container_id: str


@dataclass
class ContainerInfo:
    """Information about a running container."""
    docker_id: str
    name: str
    image: str
    status: str
    run_id: Optional[str] = None
    started_at: Optional[str] = None
    memory_usage_mb: Optional[float] = None
    cpu_percent: Optional[float] = None


class DockerRunner:
    """Manages Docker container lifecycle for financial model runs."""

    def __init__(self) -> None:
        self._client = docker.from_env()
        self._redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    def _validate_image_exists(self, image: str) -> None:
        """Check that the Docker image exists locally. Never pull."""
        try:
            self._client.images.get(image)
        except docker.errors.ImageNotFound:
            raise ImageNotFoundError(
                f"Docker image '{image}' not found locally. "
                "Images must be pre-pulled or built before use. This platform does not pull images."
            )

    def _parse_extra_args(self, extra_args: str) -> dict:
        """Parse extra_args string into Docker SDK kwargs.

        Supports:
            -e KEY=VALUE          → environment
            -v /host:/container   → volumes
            --network NAME        → network
            --memory SIZE         → mem_limit
            --cpus FLOAT          → nano_cpus
            --workdir DIR         → working_dir
            --entrypoint CMD      → entrypoint
            --name NAME           → name (ignored, we set our own)
            --rm                  → remove (ignored, we handle cleanup)
            --user USER           → user
            --label KEY=VALUE     → labels
        Other flags are logged as warnings and skipped.
        """
        if not extra_args or not extra_args.strip():
            return {}

        args = shlex.split(extra_args)
        env = {}
        volumes = {}
        kwargs = {}
        labels = {}
        i = 0

        while i < len(args):
            arg = args[i]
            if arg in ("-e", "--env") and i + 1 < len(args):
                i += 1
                kv = args[i]
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    env[k] = v
            elif arg in ("-v", "--volume") and i + 1 < len(args):
                i += 1
                parts = args[i].split(":")
                if len(parts) >= 2:
                    host_path = parts[0]
                    container_path = parts[1]
                    mode = parts[2] if len(parts) > 2 else "rw"
                    volumes[host_path] = {"bind": container_path, "mode": mode}
            elif arg == "--network" and i + 1 < len(args):
                i += 1
                kwargs["network"] = args[i]
            elif arg == "--memory" and i + 1 < len(args):
                i += 1
                kwargs["mem_limit"] = args[i]
            elif arg == "--cpus" and i + 1 < len(args):
                i += 1
                try:
                    kwargs["nano_cpus"] = int(float(args[i]) * 1e9)
                except ValueError:
                    pass
            elif arg == "--workdir" and i + 1 < len(args):
                i += 1
                kwargs["working_dir"] = args[i]
            elif arg == "--entrypoint" and i + 1 < len(args):
                i += 1
                kwargs["entrypoint"] = args[i]
            elif arg == "--user" and i + 1 < len(args):
                i += 1
                kwargs["user"] = args[i]
            elif arg == "--label" and i + 1 < len(args):
                i += 1
                if "=" in args[i]:
                    lk, lv = args[i].split("=", 1)
                    labels[lk] = lv
            elif arg in ("--rm", "--name"):
                # Skip --rm (we handle cleanup) and --name (we set our own)
                if arg == "--name" and i + 1 < len(args):
                    i += 1  # skip the name value too
            else:
                logger.warning("Unrecognized docker run arg: %s", arg)
            i += 1

        result = {}
        if env:
            result["environment"] = env
        if volumes:
            result["volumes"] = volumes
        if labels:
            result["labels"] = labels
        result.update(kwargs)
        return result

    def run_container(
        self,
        image: str,
        volumes: dict[str, dict[str, str]],
        extra_args: str,
        run_id: str,
        container_name: str,
    ) -> ContainerResult:
        """
        Run a Docker container synchronously, streaming logs to Redis pub/sub.

        Args:
            image: Docker image name:tag.
            volumes: Volume mount dict, e.g. {'/host/path': {'bind': '/container/path', 'mode': 'rw'}}.
            extra_args: Raw docker run arguments string.
            run_id: UUID of the run (used for labeling and log channel).
            container_name: Human-readable name for the container step.

        Returns:
            ContainerResult with exit code, full log text, and container ID.

        Raises:
            ImageNotFoundError: if the image doesn't exist locally.
        """
        self._validate_image_exists(image)

        # Parse extra_args into Docker SDK kwargs
        parsed = self._parse_extra_args(extra_args)

        # Merge volumes: extra_args volumes override/extend base volumes
        merged_volumes = dict(volumes)
        if "volumes" in parsed:
            merged_volumes.update(parsed.pop("volumes"))

        # Build environment from extra_args
        environment = parsed.pop("environment", {})

        # Build labels: always include our app label + run metadata
        labels = {
            "app": "almplatform",
            "run_id": run_id,
            "container_name": container_name,
        }
        if "labels" in parsed:
            labels.update(parsed.pop("labels"))

        log_channel = f"run:{run_id}:logs"

        logger.info("Starting container '%s' (image: %s) for run %s", container_name, image, run_id)

        container = self._client.containers.run(
            image=image,
            environment=environment,
            volumes=merged_volumes,
            labels=labels,
            name=f"almplatform-{run_id[:8]}-{container_name}",
            detach=True,
            stdout=True,
            stderr=True,
            **parsed,
        )

        docker_container_id = container.id
        full_log_lines: list[str] = []

        try:
            # Stream logs in real time
            for log_chunk in container.logs(stream=True, follow=True, timestamps=True):
                line = log_chunk.decode("utf-8", errors="replace").rstrip("\n")
                full_log_lines.append(line)

                # Publish each log line to Redis channel
                log_message = f"[{container_name}] {line}"
                try:
                    self._redis.publish(log_channel, log_message)
                except Exception as redis_exc:
                    logger.warning("Failed to publish log line to Redis: %s", redis_exc)

            # Wait for container to fully stop and get exit code
            result = container.wait(timeout=None)
            exit_code = result.get("StatusCode", -1)

        except Exception as exc:
            logger.error("Error while streaming container '%s' logs: %s", container_name, exc)
            try:
                container.kill()
            except Exception:
                pass
            raise
        finally:
            # Clean up the container
            try:
                container.remove(force=True)
            except Exception as rm_exc:
                logger.warning("Failed to remove container: %s", rm_exc)

        full_log = "\n".join(full_log_lines)

        # Publish completion message
        status_msg = "completed" if exit_code == 0 else f"failed (exit code {exit_code})"
        self._redis.publish(log_channel, f"[{container_name}] Container {status_msg}")

        logger.info(
            "Container '%s' finished with exit code %d for run %s",
            container_name, exit_code, run_id,
        )

        return ContainerResult(
            exit_code=exit_code,
            log=full_log,
            docker_container_id=docker_container_id,
        )

    def get_container_stats(self, docker_container_id: str) -> dict:
        """Get CPU% and memory MB for a running container."""
        try:
            container = self._client.containers.get(docker_container_id)
            stats = container.stats(stream=False)

            # Calculate CPU percent
            cpu_percent = 0.0
            cpu_delta = stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0) - \
                        stats.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
            system_delta = stats.get("cpu_stats", {}).get("system_cpu_usage", 0) - \
                           stats.get("precpu_stats", {}).get("system_cpu_usage", 0)
            num_cpus = stats.get("cpu_stats", {}).get("online_cpus", 1) or 1
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = round((cpu_delta / system_delta) * num_cpus * 100.0, 2)

            # Memory MB
            memory_usage = stats.get("memory_stats", {}).get("usage", 0)
            memory_mb = round(memory_usage / (1024 * 1024), 2) if memory_usage else 0.0

            return {"cpu_percent": cpu_percent, "memory_mb": memory_mb}
        except Exception as exc:
            logger.warning("Failed to get container stats for %s: %s", docker_container_id, exc)
            return {"cpu_percent": 0.0, "memory_mb": 0.0}

    def kill_container(self, docker_container_id: str) -> None:
        """Force-kill a running container immediately."""
        try:
            container = self._client.containers.get(docker_container_id)
            container.kill()
            logger.info("Killed container %s", docker_container_id)
        except docker.errors.NotFound:
            logger.warning("Container %s not found (already removed?)", docker_container_id)
        except docker.errors.APIError as exc:
            logger.error("Failed to kill container %s: %s", docker_container_id, exc)
            raise

    def pause_container(self, docker_container_id: str) -> None:
        """Pause a running container."""
        try:
            container = self._client.containers.get(docker_container_id)
            container.pause()
            logger.info("Paused container %s", docker_container_id)
        except docker.errors.NotFound:
            logger.warning("Container %s not found", docker_container_id)
            raise
        except docker.errors.APIError as exc:
            logger.error("Failed to pause container %s: %s", docker_container_id, exc)
            raise

    def resume_container(self, docker_container_id: str) -> None:
        """Resume a paused container."""
        try:
            container = self._client.containers.get(docker_container_id)
            container.unpause()
            logger.info("Resumed container %s", docker_container_id)
        except docker.errors.NotFound:
            logger.warning("Container %s not found", docker_container_id)
            raise
        except docker.errors.APIError as exc:
            logger.error("Failed to resume container %s: %s", docker_container_id, exc)
            raise

    def list_running_containers(self) -> list[ContainerInfo]:
        """List all running containers launched by this app (label app=almplatform)."""
        containers = self._client.containers.list(
            filters={"label": "app=almplatform", "status": "running"},
        )

        result: list[ContainerInfo] = []
        for c in containers:
            # Get stats
            stats_data = self.get_container_stats(c.short_id)

            result.append(ContainerInfo(
                docker_id=c.short_id,
                name=c.name,
                image=c.image.tags[0] if c.image.tags else str(c.image.id)[:12],
                status=c.status,
                run_id=c.labels.get("run_id"),
                started_at=c.attrs.get("State", {}).get("StartedAt"),
                memory_usage_mb=stats_data["memory_mb"],
                cpu_percent=stats_data["cpu_percent"],
            ))

        return result
