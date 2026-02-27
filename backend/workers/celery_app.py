"""Celery application configuration with Redis broker and backend."""

from celery import Celery
from celery.schedules import crontab

from backend.config import settings

celery_app = Celery(
    "almplatform",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Task routing
    task_default_queue="default",

    # Beat schedule
    beat_schedule={
        "cleanup-old-runs": {
            "task": "backend.workers.cleanup.cleanup_old_runs",
            "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM UTC
        },
        "resource-alerting": {
            "task": "backend.workers.alerting.check_resources",
            "schedule": 60.0,  # Every 60 seconds
        },
        "schedule-runner": {
            "task": "backend.workers.scheduler.process_schedules",
            "schedule": 60.0,  # Every 60 seconds
        },
    },
)

# Auto-discover tasks in the workers package
celery_app.autodiscover_tasks(["backend.workers"])
