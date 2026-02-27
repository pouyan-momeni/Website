"""Docker container runner using docker-py SDK."""

import logging
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

    def run_container(
        self,
        image: str,
        volumes: dict[str, dict[str, str]],
        env: dict[str, str],
        run_id: str,
        container_name: str,
    ) -> ContainerResult:
        """
        Run a Docker container synchronously, streaming logs to Redis pub/sub.

        Args:
            image: Docker image name:tag.
            volumes: Volume mount dict, e.g. {'/host/path': {'bind': '/container/path', 'mode': 'rw'}}.
            env: Environment variables for the container.
            run_id: UUID of the run (used for labeling and log channel).
            container_name: Human-readable name for the container step.

        Returns:
            ContainerResult with exit code, full log text, and container ID.

        Raises:
            ImageNotFoundError: if the image doesn't exist locally.
        """
        self._validate_image_exists(image)

        labels = {
            "app": "almplatform",
            "run_id": run_id,
            "container_name": container_name,
        }

        log_channel = f"run:{run_id}:logs"

        logger.info("Starting container '%s' (image: %s) for run %s", container_name, image, run_id)

        container = self._client.containers.run(
            image=image,
            environment=env,
            volumes=volumes,
            labels=labels,
            name=f"almplatform-{run_id[:8]}-{container_name}",
            detach=True,
            stdout=True,
            stderr=True,
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

    def list_running_containers(self) -> list[ContainerInfo]:
        """List all running containers launched by this app (label app=almplatform)."""
        containers = self._client.containers.list(
            filters={"label": "app=almplatform", "status": "running"},
        )

        result: list[ContainerInfo] = []
        for c in containers:
            # Get memory stats
            memory_usage_mb: Optional[float] = None
            try:
                stats = c.stats(stream=False)
                memory_usage = stats.get("memory_stats", {}).get("usage", 0)
                if memory_usage:
                    memory_usage_mb = round(memory_usage / (1024 * 1024), 2)
            except Exception:
                pass

            result.append(ContainerInfo(
                docker_id=c.short_id,
                name=c.name,
                image=c.image.tags[0] if c.image.tags else str(c.image.id)[:12],
                status=c.status,
                run_id=c.labels.get("run_id"),
                started_at=c.attrs.get("State", {}).get("StartedAt"),
                memory_usage_mb=memory_usage_mb,
            ))

        return result
