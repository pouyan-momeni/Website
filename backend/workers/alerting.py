"""Celery Beat task: monitor system resources and alert admins."""

import logging
from datetime import datetime, timedelta, timezone

import psutil
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.models.resource_alert import ResourceAlert
from backend.models.user import User
from backend.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
SyncSession = sessionmaker(bind=_sync_engine)


def _send_alert_email(subject: str, body: str, admin_emails: list[str]) -> None:
    """Send alert email to all admin users."""
    import smtplib
    from email.mime.text import MIMEText

    for email_addr in admin_emails:
        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = settings.SMTP_FROM
            msg["To"] = email_addr

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.send_message(msg)

            logger.info("Sent resource alert to %s", email_addr)
        except Exception as exc:
            logger.error("Failed to send alert email to %s: %s", email_addr, exc)


@celery_app.task(name="backend.workers.alerting.check_resources")
def check_resources() -> dict:
    """
    Check CPU and memory usage against thresholds.
    If above threshold and cooldown has elapsed, send alert emails to all admins
    and insert a resource_alerts record.
    Runs every 60 seconds via Celery Beat.
    """
    cpu_percent = psutil.cpu_percent(interval=1) / 100.0
    mem = psutil.virtual_memory()
    memory_percent = mem.percent / 100.0

    alerts_triggered: list[str] = []
    db = SyncSession()

    try:
        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.ALERT_COOLDOWN_MINUTES)

        # Get admin and developer emails
        recipients = db.execute(
            select(User).where(User.role.in_(["admin", "developer"]), User.is_active == True)  # noqa: E712
        ).scalars().all()
        admin_emails = [r.email for r in recipients if r.email]

        if not admin_emails:
            logger.debug("No admin/developer emails configured, skipping alert check")
            return {"alerts": [], "cpu": cpu_percent, "memory": memory_percent}

        # Check memory threshold
        if memory_percent >= settings.MEMORY_THRESHOLD:
            last_mem_alert = db.execute(
                select(ResourceAlert)
                .where(
                    ResourceAlert.alert_type == "memory",
                    ResourceAlert.triggered_at > cooldown_cutoff,
                )
                .order_by(ResourceAlert.triggered_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            if not last_mem_alert:
                alert = ResourceAlert(
                    alert_type="memory",
                    threshold_pct=memory_percent * 100,
                    notified=True,
                )
                db.add(alert)
                alerts_triggered.append("memory")

                _send_alert_email(
                    subject=f"[ALMPlatform ALERT] Memory at {memory_percent * 100:.1f}%",
                    body=(
                        f"Memory usage has exceeded the threshold.\n\n"
                        f"Current: {memory_percent * 100:.1f}%\n"
                        f"Threshold: {settings.MEMORY_THRESHOLD * 100:.1f}%\n"
                        f"Total: {mem.total / (1024**3):.1f} GB\n"
                        f"Used: {mem.used / (1024**3):.1f} GB\n"
                        f"Available: {mem.available / (1024**3):.1f} GB\n"
                    ),
                    admin_emails=admin_emails,
                )

        # Check CPU threshold
        if cpu_percent >= settings.CPU_ALERT_THRESHOLD:
            last_cpu_alert = db.execute(
                select(ResourceAlert)
                .where(
                    ResourceAlert.alert_type == "cpu",
                    ResourceAlert.triggered_at > cooldown_cutoff,
                )
                .order_by(ResourceAlert.triggered_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            if not last_cpu_alert:
                alert = ResourceAlert(
                    alert_type="cpu",
                    threshold_pct=cpu_percent * 100,
                    notified=True,
                )
                db.add(alert)
                alerts_triggered.append("cpu")

                _send_alert_email(
                    subject=f"[ALMPlatform ALERT] CPU at {cpu_percent * 100:.1f}%",
                    body=(
                        f"CPU usage has exceeded the threshold.\n\n"
                        f"Current: {cpu_percent * 100:.1f}%\n"
                        f"Threshold: {settings.CPU_ALERT_THRESHOLD * 100:.1f}%\n"
                        f"CPU Count: {psutil.cpu_count()}\n"
                    ),
                    admin_emails=admin_emails,
                )

        db.commit()

    except Exception as exc:
        logger.error("Resource alerting task failed: %s", exc, exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()

    return {
        "alerts": alerts_triggered,
        "cpu": round(cpu_percent, 4),
        "memory": round(memory_percent, 4),
    }
