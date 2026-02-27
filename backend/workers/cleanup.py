"""Celery Beat task: cleanup old non-archived runs (30-day retention)."""

import logging
import shutil
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.models.run import Run
from backend.models.run_container import RunContainer
from backend.models.notification import Notification
from backend.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
SyncSession = sessionmaker(bind=_sync_engine)

RETENTION_DAYS = 30


@celery_app.task(name="backend.workers.cleanup.cleanup_old_runs")
def cleanup_old_runs() -> dict:
    """
    Delete runs older than 30 days where is_archived is False.
    Removes output files and logs from disk, then deletes DB records.
    Runs daily at 2 AM UTC via Celery Beat.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    db = SyncSession()
    deleted_count = 0

    try:
        result = db.execute(
            select(Run).where(
                Run.created_at < cutoff,
                Run.is_archived == False,  # noqa: E712
            )
        )
        old_runs = result.scalars().all()

        for run in old_runs:
            run_id = str(run.id)
            logger.info("Cleaning up old run %s (created %s)", run_id, run.created_at)

            # Delete output directory from disk
            run_dir = os.path.join(settings.RUNS_BASE_PATH, run_id)
            if os.path.exists(run_dir):
                try:
                    shutil.rmtree(run_dir)
                    logger.info("Deleted run directory: %s", run_dir)
                except OSError as exc:
                    logger.error("Failed to delete run directory %s: %s", run_dir, exc)

            # Delete related records
            db.execute(delete(Notification).where(Notification.run_id == run.id))
            db.execute(delete(RunContainer).where(RunContainer.run_id == run.id))
            db.delete(run)
            deleted_count += 1

        db.commit()
        logger.info("Cleanup complete: deleted %d old runs", deleted_count)

    except Exception as exc:
        logger.error("Cleanup task failed: %s", exc, exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()

    return {"deleted": deleted_count, "cutoff": cutoff.isoformat()}
