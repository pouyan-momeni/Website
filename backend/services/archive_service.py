"""Service for archiving completed runs to long-term storage."""

import logging
import os
import shutil
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.model import Model
from backend.models.run import Run
from backend.models.user import User

logger = logging.getLogger(__name__)


async def archive_run(db: AsyncSession, run_id: UUID, user_id: UUID) -> Run:
    """
    Archive a run by copying its output directory to the archive path.

    Archive structure: {ARCHIVE_BASE_PATH}/{ldap_username}/{model_slug}/{YYYY-MM-DD}/{run_id}/

    Sets is_archived=true, archive_path, and archived_at on the run record.
    """
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    if run.is_archived:
        raise ValueError(f"Run {run_id} is already archived")

    if run.status not in ("completed", "failed", "cancelled"):
        raise ValueError(f"Cannot archive run with status '{run.status}'. Must be completed, failed, or cancelled.")

    # Get user and model for archive path
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User {user_id} not found")

    model_result = await db.execute(select(Model).where(Model.id == run.model_id))
    model = model_result.scalar_one_or_none()
    model_slug = model.slug if model else "unknown"

    # Build archive path
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_path = os.path.join(
        settings.ARCHIVE_BASE_PATH,
        user.ldap_username,
        model_slug,
        date_str,
        str(run_id),
    )

    # Copy run directory to archive
    source_dir = os.path.join(settings.RUNS_BASE_PATH, str(run_id))
    if os.path.exists(source_dir):
        try:
            os.makedirs(os.path.dirname(archive_path), exist_ok=True)
            shutil.copytree(source_dir, archive_path, dirs_exist_ok=True)
            logger.info("Archived run %s to %s", run_id, archive_path)
        except OSError as exc:
            logger.error("Failed to archive run %s: %s", run_id, exc)
            raise ValueError(f"Failed to copy run files to archive: {exc}") from exc
    else:
        # Create empty archive directory even if source doesn't exist
        os.makedirs(archive_path, exist_ok=True)
        logger.warning("Source directory %s not found, created empty archive at %s", source_dir, archive_path)

    # Update run record
    run.is_archived = True
    run.archived_at = datetime.now(timezone.utc)
    run.archive_path = archive_path
    await db.flush()

    return run
