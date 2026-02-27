"""Service for creating and managing model runs."""

import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.model import Model
from backend.models.run import Run


async def create_run(
    db: AsyncSession,
    model_id: uuid.UUID,
    user_id: uuid.UUID,
    inputs: dict,
    config_override: dict,
) -> Run:
    """
    Create a new run for a model.

    Resolves the merged config (model default + override), creates the run record
    with status 'queued', assigns a queue position, creates the output directory,
    and enqueues the Celery task.

    Returns the created Run ORM object.
    """
    # Fetch the model
    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise ValueError(f"Model {model_id} not found")

    # Merge config: default + override
    merged_config = dict(model.default_config or {})
    if config_override:
        for key, value in config_override.items():
            if key in merged_config:
                if isinstance(merged_config[key], dict):
                    merged_config[key]["value"] = value
                else:
                    merged_config[key] = value
            else:
                merged_config[key] = value

    # Determine queue position
    max_pos_result = await db.execute(
        select(func.max(Run.queue_position)).where(Run.status == "queued")
    )
    max_pos = max_pos_result.scalar_one_or_none()
    next_pos = (max_pos or 0) + 1

    # Create run directory
    run_id = uuid.uuid4()
    output_path = os.path.join(settings.RUNS_BASE_PATH, str(run_id), "outputs")
    log_path = os.path.join(settings.RUNS_BASE_PATH, str(run_id), "logs")
    os.makedirs(output_path, exist_ok=True)
    os.makedirs(log_path, exist_ok=True)

    # Create run record
    run = Run(
        id=run_id,
        model_id=model_id,
        triggered_by=user_id,
        status="queued",
        inputs=inputs,
        config_snapshot=merged_config,
        queue_position=next_pos,
        output_path=output_path,
        log_path=log_path,
    )
    db.add(run)
    await db.flush()

    # Enqueue Celery task
    from backend.workers.execute_run import execute_model_run
    task = execute_model_run.delay(str(run_id))
    run.celery_task_id = task.id
    await db.flush()

    return run
