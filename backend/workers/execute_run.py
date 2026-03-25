"""Celery task for executing a model run through its Docker container pipeline."""

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import redis
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings
from backend.docker_runner.runner import DockerRunner, ImageNotFoundError
from backend.models.model import Model
from backend.models.notification import Notification
from backend.models.run import Run
from backend.models.run_container import RunContainer
from backend.models.user import User
from backend.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Sync engine for use inside Celery tasks
_sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
SyncSession = sessionmaker(bind=_sync_engine)

MAX_CONTAINER_RETRIES = 3
RETRY_DELAY_SECONDS = 30

redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


class ResourceGuard:
    """Check whether the system has enough resources to start a new run."""

    @staticmethod
    def can_start() -> bool:
        """Return True if memory usage is below the configured threshold."""
        import psutil
        mem = psutil.virtual_memory()
        memory_pct = mem.percent / 100.0
        if memory_pct >= settings.MEMORY_THRESHOLD:
            logger.warning(
                "Resource guard: memory at %.1f%% (threshold %.1f%%). Cannot start run.",
                memory_pct * 100, settings.MEMORY_THRESHOLD * 100,
            )
            return False
        return True


def _send_notification_sync(db: Session, run: Run, event: str) -> None:
    """Send email notification for a run event (sync version for Celery)."""
    try:
        user = db.execute(select(User).where(User.id == run.triggered_by)).scalar_one_or_none()
        if not user or not user.email:
            logger.warning("No email for user %s, skipping notification", run.triggered_by)
            return

        model = db.execute(select(Model).where(Model.id == run.model_id)).scalar_one_or_none()
        model_name = model.name if model else "Unknown"

        duration = ""
        if run.started_at and run.completed_at:
            delta = run.completed_at - run.started_at
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            duration = f"{hours}h {minutes}m {seconds}s"

        # Import here to avoid circular deps; use sync email sending in Celery
        import smtplib
        from email.mime.text import MIMEText

        subject = f"[ALMPlatform] Run {event}: {model_name}"
        body = (
            f"Run ID: {run.id}\n"
            f"Model: {model_name}\n"
            f"Status: {event}\n"
            f"Duration: {duration or 'N/A'}\n"
            f"Link: {settings.APP_BASE_URL}/runs/{run.id}\n"
        )

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = user.email

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.send_message(msg)

        notification = Notification(
            user_id=user.id,
            run_id=run.id,
            event=event,
            success=True,
        )
        db.add(notification)
        db.commit()

        logger.info("Sent '%s' notification for run %s to %s", event, run.id, user.email)

    except Exception as exc:
        logger.error("Failed to send notification for run %s: %s", run.id, exc)
        try:
            notification = Notification(
                user_id=run.triggered_by,
                run_id=run.id,
                event=event,
                success=False,
            )
            db.add(notification)
            db.commit()
        except Exception:
            pass


@celery_app.task(
    bind=True,
    name="backend.workers.execute_run.execute_model_run",
    max_retries=None,
    default_retry_delay=60,
)
def execute_model_run(self, run_id: str) -> dict:
    """
    Execute a model run by sequentially running its Docker containers.

    Checks resource availability before starting. Retries with 60s delay if
    resources are insufficient. Each container is retried up to 3 times on failure.
    Checks for cancellation before each container step.
    """
    # Check resource guard
    if not ResourceGuard.can_start():
        logger.info("Resources insufficient for run %s, retrying in 60s", run_id)
        raise self.retry(countdown=60)

    db = SyncSession()
    docker_runner = DockerRunner()

    try:
        run = db.execute(select(Run).where(Run.id == run_id)).scalar_one_or_none()
        if not run:
            logger.error("Run %s not found", run_id)
            return {"status": "error", "detail": "Run not found"}

        model = db.execute(select(Model).where(Model.id == run.model_id)).scalar_one_or_none()
        if not model:
            logger.error("Model %s not found for run %s", run.model_id, run_id)
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {"status": "error", "detail": "Model not found"}

        # Mark run as running
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        run.queue_position = None
        db.commit()

        # Publish status update
        redis_client.publish(f"run:{run_id}:logs", "[system] Run started")

        # Sort container images by order
        docker_images = sorted(model.docker_images, key=lambda x: x.get("order", 0))

        # Prepare volume mounts
        output_dir = os.path.join(settings.RUNS_BASE_PATH, run_id, "outputs")
        log_dir = os.path.join(settings.RUNS_BASE_PATH, run_id, "logs")
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)

        volumes = {
            settings.SHARED_NAS_PATH: {"bind": "/data/input", "mode": "ro"},
            output_dir: {"bind": "/data/output", "mode": "rw"},
            log_dir: {"bind": "/data/logs", "mode": "rw"},
        }

        for idx, img_spec in enumerate(docker_images):
            container_name = img_spec.get("name", f"step-{idx}")
            image = img_spec["image"]

            # ── Check cancellation ──
            cancel_key = f"run:{run_id}:cancel"
            if redis_client.get(cancel_key):
                logger.info("Run %s cancelled before container '%s'", run_id, container_name)
                run.status = "cancelled"
                run.completed_at = datetime.now(timezone.utc)
                db.commit()
                redis_client.publish(f"run:{run_id}:logs", "[system] Run cancelled by user")
                _send_notification_sync(db, run, "cancelled")
                return {"status": "cancelled"}

            # ── Create run_container record ──
            run_container = RunContainer(
                run_id=run.id,
                container_name=container_name,
                status="running",
                started_at=datetime.now(timezone.utc),
                log_file=os.path.join(log_dir, f"{container_name}.log"),
            )
            db.add(run_container)
            run.current_container_index = idx
            db.commit()

            # ── Prepare extra_args ──
            # Start with the model-configured extra_args
            extra_args_parts = []
            model_extra_args = img_spec.get("extra_args", "")
            if model_extra_args:
                extra_args_parts.append(model_extra_args.strip())

            # Add run-specific env vars as -e flags
            run_env = {
                "RUN_ID": run_id,
                "MODEL_SLUG": model.slug,
                "OUTPUT_DIR": "/data/output",
                "LOG_DIR": "/data/logs",
            }
            # Add config snapshot as env vars
            if run.config_snapshot:
                for key, val in run.config_snapshot.items():
                    config_val = val.get("value", val) if isinstance(val, dict) else val
                    run_env[f"CONFIG_{key.upper()}"] = str(config_val)
            # Add inputs as env vars
            if run.inputs:
                for key, val in run.inputs.items():
                    run_env[f"INPUT_{key.upper()}"] = str(val)

            for k, v in run_env.items():
                extra_args_parts.append(f"-e {k}={v}")

            extra_args = "\n".join(extra_args_parts)

            # ── Run container with retries ──
            success = False
            last_error = ""

            for attempt in range(1, MAX_CONTAINER_RETRIES + 1):
                try:
                    redis_client.publish(
                        f"run:{run_id}:logs",
                        f"[system] Starting container '{container_name}' (attempt {attempt}/{MAX_CONTAINER_RETRIES})"
                    )

                    result = docker_runner.run_container(
                        image=image,
                        volumes=volumes,
                        extra_args=extra_args,
                        run_id=run_id,
                        container_name=container_name,
                        run_inputs=run.inputs or {},
                    )

                    # Write log to file
                    log_file_path = os.path.join(log_dir, f"{container_name}.log")
                    Path(log_file_path).write_text(result.log, encoding="utf-8")

                    run_container.docker_container_id = result.docker_container_id
                    run_container.exit_code = result.exit_code
                    run_container.retry_count = attempt - 1

                    if result.exit_code == 0:
                        run_container.status = "completed"
                        run_container.completed_at = datetime.now(timezone.utc)
                        db.commit()
                        success = True
                        break
                    else:
                        last_error = f"Exit code {result.exit_code}"
                        logger.warning(
                            "Container '%s' failed (attempt %d/%d): %s",
                            container_name, attempt, MAX_CONTAINER_RETRIES, last_error,
                        )
                        run_container.retry_count = attempt

                        if attempt < MAX_CONTAINER_RETRIES:
                            redis_client.publish(
                                f"run:{run_id}:logs",
                                f"[system] Container '{container_name}' failed, retrying in {RETRY_DELAY_SECONDS}s..."
                            )
                            db.commit()
                            time.sleep(RETRY_DELAY_SECONDS)

                            # Check cancellation during retry wait
                            if redis_client.get(cancel_key):
                                run.status = "cancelled"
                                run.completed_at = datetime.now(timezone.utc)
                                run_container.status = "cancelled"
                                db.commit()
                                _send_notification_sync(db, run, "cancelled")
                                return {"status": "cancelled"}

                except ImageNotFoundError as exc:
                    if settings.is_develop:
                        logger.info("Dev mode logic: Simulating successful container '%s'", container_name)
                        redis_client.publish(
                            f"run:{run_id}:logs",
                            f"[{container_name}] (Dev Mode) Simulating container execution..."
                        )
                        # Simulate execution time so the run appears in Queue/Monitoring
                        time.sleep(3)
                        redis_client.publish(
                            f"run:{run_id}:logs",
                            f"[{container_name}] (Dev Mode) Container completed successfully"
                        )
                        run_container.docker_container_id = f"dev-mock-{container_name}"
                        run_container.exit_code = 0
                        run_container.status = "completed"
                        run_container.completed_at = datetime.now(timezone.utc)
                        db.commit()
                        success = True
                        break
                    else:
                        last_error = str(exc)
                        logger.error("Image not found for container '%s': %s", container_name, exc)
                        run_container.status = "failed"
                        run_container.exit_code = -1
                        run_container.completed_at = datetime.now(timezone.utc)
                        db.commit()
                        break

                except Exception as exc:
                    last_error = str(exc)
                    logger.error(
                        "Container '%s' error (attempt %d/%d): %s",
                        container_name, attempt, MAX_CONTAINER_RETRIES, exc,
                    )
                    run_container.retry_count = attempt

                    if attempt < MAX_CONTAINER_RETRIES:
                        db.commit()
                        time.sleep(RETRY_DELAY_SECONDS)
                    else:
                        break

            if not success:
                # Container failed after all retries
                run_container.status = "failed"
                run_container.completed_at = datetime.now(timezone.utc)
                run.status = "failed"
                run.completed_at = datetime.now(timezone.utc)
                db.commit()

                redis_client.publish(
                    f"run:{run_id}:logs",
                    f"[system] Run failed at container '{container_name}': {last_error}"
                )
                _send_notification_sync(db, run, "failed")
                return {"status": "failed", "detail": f"Container '{container_name}' failed: {last_error}"}

        # Generate mock outputs in development mode
        if settings.is_develop:
            try:
                from backend.api.runs import _generate_sample_outputs
                _generate_sample_outputs(run_id, output_dir, model.name)
                logger.info("Generated sample outputs for dev run %s", run_id)
            except Exception as e:
                logger.error("Failed to generate sample outputs: %s", e)

        # All containers completed successfully
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

        redis_client.publish(f"run:{run_id}:logs", "[system] Run completed successfully")
        _send_notification_sync(db, run, "completed")

        logger.info("Run %s completed successfully", run_id)
        return {"status": "completed"}

    except Exception as exc:
        logger.error("Unexpected error executing run %s: %s", run_id, exc, exc_info=True)
        try:
            run = db.execute(select(Run).where(Run.id == run_id)).scalar_one_or_none()
            if run and run.status == "running":
                run.status = "failed"
                run.completed_at = datetime.now(timezone.utc)
                db.commit()
                _send_notification_sync(db, run, "failed")
        except Exception:
            pass
        raise

    finally:
        db.close()
