"""Celery Beat task: process scheduled model runs."""

import logging
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.models.model import Model
from backend.models.run import Run
from backend.models.schedule import Schedule
from backend.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
SyncSession = sessionmaker(bind=_sync_engine)


@celery_app.task(name="backend.workers.scheduler.process_schedules")
def process_schedules() -> dict:
    """
    Query active schedules where next_run_at <= now().
    For each due schedule: create a run record, enqueue execute_model_run,
    and update next_run_at using croniter.
    Runs every 60 seconds via Celery Beat.
    """
    now = datetime.now(timezone.utc)
    db = SyncSession()
    processed = 0

    try:
        result = db.execute(
            select(Schedule).where(
                Schedule.is_active == True,  # noqa: E712
                Schedule.next_run_at <= now,
            )
        )
        due_schedules = result.scalars().all()

        for schedule in due_schedules:
            try:
                model = db.execute(
                    select(Model).where(Model.id == schedule.model_id)
                ).scalar_one_or_none()

                if not model:
                    logger.warning("Schedule %s references non-existent model %s", schedule.id, schedule.model_id)
                    continue

                # Merge configs: model default + schedule override
                merged_config = dict(model.default_config or {})
                if schedule.config:
                    merged_config.update(schedule.config)

                # Determine queue position
                max_pos_result = db.execute(
                    select(Run.queue_position)
                    .where(Run.status == "queued")
                    .order_by(Run.queue_position.desc())
                    .limit(1)
                )
                max_pos = max_pos_result.scalar_one_or_none()
                next_pos = (max_pos or 0) + 1

                # Create run record
                import os
                import uuid

                run_id = uuid.uuid4()
                output_path = os.path.join(settings.RUNS_BASE_PATH, str(run_id), "outputs")
                log_path = os.path.join(settings.RUNS_BASE_PATH, str(run_id), "logs")
                os.makedirs(output_path, exist_ok=True)
                os.makedirs(log_path, exist_ok=True)

                run = Run(
                    id=run_id,
                    model_id=schedule.model_id,
                    triggered_by=schedule.created_by,
                    status="queued",
                    inputs=schedule.inputs or {},
                    config_snapshot=merged_config,
                    queue_position=next_pos,
                    output_path=output_path,
                    log_path=log_path,
                )
                db.add(run)

                # Update schedule
                schedule.last_run_at = now
                cron_iter = croniter(schedule.cron_expression, now)
                schedule.next_run_at = cron_iter.get_next(datetime)

                db.commit()

                # Enqueue Celery task
                from backend.workers.execute_run import execute_model_run
                task = execute_model_run.delay(str(run_id))
                run.celery_task_id = task.id
                db.commit()

                logger.info(
                    "Scheduled run %s created for model '%s' (schedule %s)",
                    run_id, model.name, schedule.id,
                )
                processed += 1

            except Exception as exc:
                logger.error("Failed to process schedule %s: %s", schedule.id, exc, exc_info=True)
                db.rollback()

    except Exception as exc:
        logger.error("Schedule processing task failed: %s", exc, exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()

    return {"processed": processed}
