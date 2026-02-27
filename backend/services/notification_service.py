"""Service for sending email notifications for run events."""

import logging
from uuid import UUID

import aiosmtplib
from email.mime.text import MIMEText
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.model import Model
from backend.models.notification import Notification
from backend.models.run import Run
from backend.models.user import User

logger = logging.getLogger(__name__)


async def send_run_notification(db: AsyncSession, run_id: UUID, event: str) -> None:
    """
    Send an email notification for a run event (completed, failed, cancelled).

    Looks up the run's triggering user and sends an email with:
    - Run ID
    - Model name
    - Status
    - Duration
    - Direct link to /runs/{run_id}

    Inserts a notification record tracking success/failure.
    """
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        logger.error("Cannot send notification: run %s not found", run_id)
        return

    user_result = await db.execute(select(User).where(User.id == run.triggered_by))
    user = user_result.scalar_one_or_none()
    if not user or not user.email:
        logger.warning("No email for user %s, skipping notification", run.triggered_by)
        return

    model_result = await db.execute(select(Model).where(Model.id == run.model_id))
    model = model_result.scalar_one_or_none()
    model_name = model.name if model else "Unknown Model"

    # Calculate duration
    duration = "N/A"
    if run.started_at and run.completed_at:
        delta = run.completed_at - run.started_at
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        duration = f"{hours}h {minutes}m {seconds}s"

    # Build email
    subject = f"[ALMPlatform] Run {event}: {model_name}"
    body = (
        f"Run ID: {run.id}\n"
        f"Model: {model_name}\n"
        f"Status: {event}\n"
        f"Duration: {duration}\n"
        f"Link: {settings.APP_BASE_URL}/runs/{run.id}\n"
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = user.email

    success = True
    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
        )
        logger.info("Sent '%s' notification for run %s to %s", event, run_id, user.email)
    except Exception as exc:
        logger.error("Failed to send notification for run %s: %s", run_id, exc)
        success = False

    # Record notification
    notification = Notification(
        user_id=user.id,
        run_id=run.id,
        event=event,
        success=success,
    )
    db.add(notification)
    await db.flush()
