"""Schedules API routes — cron-style scheduling for model runs."""

import uuid
import threading
import time as _time
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.auth.dependencies import require_role, get_current_user
from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


# ─── In-memory store (dev mode) ─────────────────────────────────────────────

_DEV_SCHEDULES: dict[str, dict] = {}


class ScheduleCreateBody(BaseModel):
    model_id: str
    model_name: Optional[str] = None
    scheduled_at: str  # ISO datetime string for the first run
    repeat_type: str = "none"  # none | daily | weekly | monthly | custom
    cron_expression: Optional[str] = None  # only used when repeat_type == "custom"
    repeat_count: Optional[int] = None  # None = unlimited, otherwise number of repeats
    inputs: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None


class ScheduleUpdateBody(BaseModel):
    scheduled_at: Optional[str] = None
    repeat_type: Optional[str] = None
    cron_expression: Optional[str] = None
    repeat_count: Optional[int] = None
    is_active: Optional[bool] = None
    inputs: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None


def _calculate_next_run(scheduled_at_str: str, repeat_type: str, cron_expression: Optional[str] = None) -> Optional[str]:
    """Calculate the next run time based on repeat settings."""
    try:
        scheduled_at = datetime.fromisoformat(scheduled_at_str.replace("Z", "+00:00"))
        # Ensure timezone awareness
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    except Exception:
        return None

    now = datetime.now(timezone.utc)
    if scheduled_at > now:
        return scheduled_at.isoformat()

    if repeat_type == "none":
        return scheduled_at.isoformat()

    # For repeating schedules, find the next occurrence after now
    if repeat_type == "daily":
        delta = timedelta(days=1)
    elif repeat_type == "weekly":
        delta = timedelta(weeks=1)
    elif repeat_type == "monthly":
        delta = timedelta(days=30)  # Approximate
    elif repeat_type == "custom" and cron_expression:
        try:
            from croniter import croniter
            if croniter.is_valid(cron_expression):
                cron_iter = croniter(cron_expression, now)
                return cron_iter.get_next(datetime).isoformat()
        except ImportError:
            pass
        return None
    else:
        return None

    next_run = scheduled_at
    while next_run <= now:
        next_run += delta
    return next_run.isoformat()


@router.get("")
async def list_schedules(current_user=Depends(get_current_user)):
    """List all schedules."""
    if settings.is_develop:
        schedules = list(_DEV_SCHEDULES.values())
        schedules.sort(key=lambda s: s.get("next_run_at") or "9999", reverse=False)
        return schedules

    # Production: use DB
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.database import get_db
    from backend.models.schedule import Schedule
    # This path would need proper DI; for now, dev mode is primary
    return []


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleCreateBody,
    current_user=Depends(require_role(["admin", "developer", "runner"])),
):
    """Create a new scheduled run."""
    schedule_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    next_run = _calculate_next_run(body.scheduled_at, body.repeat_type, body.cron_expression)

    schedule = {
        "id": schedule_id,
        "model_id": body.model_id,
        "model_name": body.model_name or "Unknown Model",
        "created_by": str(current_user.id),
        "created_by_username": current_user.ldap_username,
        "scheduled_at": body.scheduled_at,
        "repeat_type": body.repeat_type,
        "cron_expression": body.cron_expression,
        "repeat_count": body.repeat_count,
        "executions_done": 0,
        "inputs": body.inputs or {},
        "config": body.config or {},
        "is_active": True,
        "next_run_at": next_run,
        "last_run_at": None,
        "created_at": now,
    }

    if settings.is_develop:
        _DEV_SCHEDULES[schedule_id] = schedule
    else:
        pass  # DB insert in production

    logger.info("Schedule created: %s for model %s, next run: %s", schedule_id, body.model_name, next_run)

    from backend.api.audit import log_action
    from backend.database import get_db
    from sqlalchemy.ext.asyncio import AsyncSession
    # Get a DB session for audit logging
    async for db in get_db():
        await log_action(
            username=current_user.ldap_username, user_id=str(current_user.id),
            action="create_schedule", resource_type="schedule", resource_id=schedule_id,
            details={"model_name": body.model_name, "repeat_type": body.repeat_type, "scheduled_at": body.scheduled_at},
            db=db,
        )
        break

    return schedule


@router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdateBody,
    current_user=Depends(require_role(["admin", "developer", "runner"])),
):
    """Update a schedule."""
    if settings.is_develop:
        schedule = _DEV_SCHEDULES.get(schedule_id)
        if not schedule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

        if body.scheduled_at is not None:
            schedule["scheduled_at"] = body.scheduled_at
        if body.repeat_type is not None:
            schedule["repeat_type"] = body.repeat_type
        if body.cron_expression is not None:
            schedule["cron_expression"] = body.cron_expression
        if body.repeat_count is not None:
            schedule["repeat_count"] = body.repeat_count
        if body.is_active is not None:
            schedule["is_active"] = body.is_active
        if body.inputs is not None:
            schedule["inputs"] = body.inputs
        if body.config is not None:
            schedule["config"] = body.config

        # Recalculate next run
        schedule["next_run_at"] = _calculate_next_run(
            schedule["scheduled_at"],
            schedule["repeat_type"],
            schedule.get("cron_expression"),
        )

        return schedule

    raise HTTPException(status_code=501, detail="Production mode not implemented")


@router.post("/{schedule_id}/toggle")
async def toggle_schedule(
    schedule_id: str,
    current_user=Depends(require_role(["admin", "developer", "runner"])),
):
    """Toggle a schedule active/inactive."""
    if settings.is_develop:
        schedule = _DEV_SCHEDULES.get(schedule_id)
        if not schedule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
        schedule["is_active"] = not schedule["is_active"]
        return schedule

    raise HTTPException(status_code=501, detail="Production mode not implemented")


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    current_user=Depends(require_role(["admin", "developer", "runner"])),
):
    """Delete a schedule."""
    if settings.is_develop:
        if schedule_id not in _DEV_SCHEDULES:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
        del _DEV_SCHEDULES[schedule_id]
        return {"detail": "Schedule deleted"}

    raise HTTPException(status_code=501, detail="Production mode not implemented")


# ─── Background schedule executor ──────────────────────────────────────────

def _execute_due_schedules():
    """Background loop: every 30s, check for due schedules and trigger runs."""
    while True:
        _time.sleep(30)
        try:
            now = datetime.now(timezone.utc)
            for sched_id, sched in list(_DEV_SCHEDULES.items()):
                if not sched.get("is_active"):
                    continue

                next_run_str = sched.get("next_run_at")
                if not next_run_str:
                    continue

                try:
                    next_run = datetime.fromisoformat(next_run_str.replace("Z", "+00:00"))
                    if next_run.tzinfo is None:
                        next_run = next_run.replace(tzinfo=timezone.utc)
                except Exception:
                    continue

                if next_run > now:
                    continue

                # ── Time to execute this schedule ──
                logger.info("Schedule %s is due (next_run=%s, now=%s) — triggering run", sched_id, next_run_str, now.isoformat())

                # Update schedule state FIRST (before trigger) to prevent infinite re-firing
                sched["last_run_at"] = now.isoformat()
                sched["executions_done"] = sched.get("executions_done", 0) + 1

                # Check if schedule is exhausted and remove it
                should_delete = False
                if sched.get("repeat_count") is not None and sched["executions_done"] >= sched["repeat_count"]:
                    should_delete = True
                    logger.info("Schedule %s exhausted after %d executions — will remove", sched_id, sched["executions_done"])
                elif sched["repeat_type"] == "none":
                    should_delete = True
                    logger.info("One-time schedule %s completed — will remove", sched_id)
                else:
                    # Calculate next occurrence
                    sched["next_run_at"] = _calculate_next_run(
                        now.isoformat(),
                        sched["repeat_type"],
                        sched.get("cron_expression"),
                    )
                    logger.info("Schedule %s next run: %s", sched_id, sched["next_run_at"])

                if should_delete:
                    del _DEV_SCHEDULES[sched_id]

                # Now trigger the run (non-fatal — even if this fails, schedule is updated)
                try:
                    _trigger_run_for_schedule(sched)
                except Exception as exc:
                    logger.error("Failed to trigger run for schedule %s: %s", sched_id, exc)

        except Exception as exc:
            logger.error("Schedule executor error: %s", exc)


def _trigger_run_for_schedule(sched: dict):
    """Create a run from a schedule using the dev run store."""
    import os
    import uuid as uuid_mod

    from backend.api.runs import _DEV_RUNS, _DEV_LOGS, _simulate_run, _get_model_config, _get_model_name

    run_id = str(uuid_mod.uuid4())
    model_id = sched["model_id"]

    default_config = _get_model_config(model_id)
    config_override = sched.get("config", {})
    if config_override:
        for key, value in config_override.items():
            if key in default_config:
                if isinstance(default_config[key], dict):
                    default_config[key]["value"] = value
                else:
                    default_config[key] = value
            else:
                default_config[key] = value

    queued_runs = [r for r in _DEV_RUNS.values() if r["status"] == "queued"]
    max_pos = max((r.get("queue_position", 0) for r in queued_runs), default=0)

    output_path = f"/tmp/alm-runs/{run_id}/outputs"
    log_path = f"/tmp/alm-runs/{run_id}/logs"
    os.makedirs(output_path, exist_ok=True)
    os.makedirs(log_path, exist_ok=True)

    run = {
        "id": run_id,
        "model_id": model_id,
        "model_name": _get_model_name(model_id),
        "username": sched.get("created_by_username", "scheduler"),
        "triggered_by": sched.get("created_by", "scheduler"),
        "status": "queued",
        "inputs": sched.get("inputs", {}),
        "config_snapshot": default_config,
        "celery_task_id": None,
        "current_container_index": 0,
        "queue_position": max_pos + 1,
        "started_at": None,
        "completed_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_archived": False,
        "archived_at": None,
        "archive_path": None,
        "output_path": output_path,
        "log_path": log_path,
    }
    _DEV_RUNS[run_id] = run
    _DEV_LOGS[run_id] = [f"[system] Run {run_id} triggered by schedule {sched['id']}"]

    thread = threading.Thread(target=_simulate_run, args=(run_id,), daemon=True)
    thread.start()

    # Audit log from background thread — use sync DB to avoid async event loop issues
    try:
        import uuid as _uuid
        from backend.models.audit_log import AuditLog as AuditLogModel
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session as SyncSession
        sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        with SyncSession(sync_engine) as session:
            # Convert string IDs to proper UUIDs for the DB
            user_id_val = None
            try:
                user_id_val = _uuid.UUID(sched.get("created_by", ""))
            except (ValueError, AttributeError):
                pass
            resource_id_val = None
            try:
                resource_id_val = _uuid.UUID(run_id)
            except (ValueError, AttributeError):
                pass
            entry = AuditLogModel(
                username=sched.get("created_by_username", "scheduler"),
                user_id=user_id_val,
                action="scheduled_run_triggered",
                resource_type="run",
                resource_id=resource_id_val,
                details={"schedule_id": sched["id"], "model_name": sched.get("model_name", "Unknown")},
            )
            session.add(entry)
            session.commit()
            logger.info("Audit logged scheduled_run_triggered for run %s", run_id)
        sync_engine.dispose()
    except Exception as exc:
        logger.warning("Failed to audit log scheduled run: %s", exc)

    logger.info("Triggered run %s for schedule %s (model: %s)", run_id, sched["id"], sched.get("model_name"))


# Start the executor in dev mode
if settings.is_develop:
    _executor_thread = threading.Thread(target=_execute_due_schedules, daemon=True, name="schedule-executor")
    _executor_thread.start()
    logger.info("Schedule executor started (checking every 30s)")
