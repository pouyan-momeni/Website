"""Audit Log API routes — captures user actions across the platform."""

import csv
import io
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.config import settings
from backend.database import get_db
from backend.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])

# ─── In-memory audit log store (dev mode fallback when DB unavailable) ─────
_AUDIT_LOG: list[dict] = []
_MAX_AUDIT_ENTRIES = 500


class AuditEntry(BaseModel):
    id: str
    timestamp: str
    user_id: str
    username: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    ip_address: Optional[str] = None


async def log_action(
    username: str,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    db: Optional[AsyncSession] = None,
):
    """Record an audit log entry. Called from other API modules.

    When a db session is provided, persists to the audit_logs table.
    Otherwise falls back to in-memory storage (dev mode without DB).
    """
    if db is not None:
        try:
            # Parse resource_id as UUID if it looks like one, otherwise store None
            rid = None
            if resource_id:
                try:
                    rid = uuid.UUID(resource_id)
                except ValueError:
                    rid = None

            uid = None
            if user_id:
                try:
                    uid = uuid.UUID(user_id)
                except ValueError:
                    uid = None

            entry = AuditLog(
                user_id=uid,
                username=username,
                action=action,
                resource_type=resource_type,
                resource_id=rid,
                details=details or {},
                ip_address=ip_address,
            )
            db.add(entry)
            await db.flush()
            logger.info("AUDIT: user=%s action=%s resource=%s/%s", username, action, resource_type, resource_id or "-")
            return
        except Exception as exc:
            logger.warning("Failed to persist audit log to DB, falling back to memory: %s", exc)

    # Fallback: in-memory store for dev mode
    entry_dict = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "username": username,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details or {},
        "ip_address": ip_address,
    }
    _AUDIT_LOG.insert(0, entry_dict)
    if len(_AUDIT_LOG) > _MAX_AUDIT_ENTRIES:
        _AUDIT_LOG[:] = _AUDIT_LOG[:_MAX_AUDIT_ENTRIES]

    logger.info("AUDIT (mem): user=%s action=%s resource=%s/%s", username, action, resource_type, resource_id or "-")


def _build_filters(
    username: Optional[str],
    action: Optional[str],
    resource_type: Optional[str],
    from_date: Optional[datetime],
    to_date: Optional[datetime],
):
    """Build SQLAlchemy filter conditions for audit log queries."""
    conditions = []
    if username:
        conditions.append(AuditLog.username == username)
    if action:
        conditions.append(AuditLog.action == action)
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if from_date:
        conditions.append(AuditLog.timestamp >= from_date)
    if to_date:
        # If date-only (no time component), include the full day
        if to_date.hour == 0 and to_date.minute == 0 and to_date.second == 0:
            conditions.append(AuditLog.timestamp < to_date + timedelta(days=1))
        else:
            conditions.append(AuditLog.timestamp <= to_date)
    return conditions


@router.get("")
async def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    username: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get audit log entries with filtering and pagination."""
    # DB path
    if db is not None:
        conditions = _build_filters(username, action, resource_type, from_date, to_date)

        # Total count
        count_q = select(func.count(AuditLog.id))
        if conditions:
            count_q = count_q.where(and_(*conditions))
        total = (await db.execute(count_q)).scalar() or 0

        # Paginated results
        query = select(AuditLog).order_by(AuditLog.timestamp.desc())
        if conditions:
            query = query.where(and_(*conditions))
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        rows = result.scalars().all()

        entries = [
            {
                "id": str(r.id),
                "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                "user_id": str(r.user_id) if r.user_id else "",
                "username": r.username,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": str(r.resource_id) if r.resource_id else None,
                "details": r.details or {},
                "ip_address": r.ip_address,
            }
            for r in rows
        ]

        return {"entries": entries, "total": total, "page": page, "page_size": page_size}

    # Fallback: in-memory list (dev mode without DB)
    entries = list(_AUDIT_LOG)
    if username:
        entries = [e for e in entries if e["username"] == username]
    if action:
        entries = [e for e in entries if e["action"] == action]
    if resource_type:
        entries = [e for e in entries if e["resource_type"] == resource_type]
    if from_date:
        entries = [e for e in entries if e["timestamp"] >= from_date.isoformat()]
    if to_date:
        entries = [e for e in entries if e["timestamp"] <= to_date.isoformat()]

    total = len(entries)
    start = (page - 1) * page_size
    end = start + page_size

    return {"entries": entries[start:end], "total": total, "page": page, "page_size": page_size}


@router.get("/export-csv")
async def export_audit_csv(
    username: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export filtered audit log entries as CSV download."""
    rows = []
    if db is not None:
        conditions = _build_filters(username, action, resource_type, from_date, to_date)
        query = select(AuditLog).order_by(AuditLog.timestamp.desc())
        if conditions:
            query = query.where(and_(*conditions))
        result = await db.execute(query)
        for r in result.scalars().all():
            rows.append({
                "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                "username": r.username,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": str(r.resource_id) if r.resource_id else "",
                "details": str(r.details or {}),
                "ip_address": r.ip_address or "",
            })
    else:
        entries = list(_AUDIT_LOG)
        if username:
            entries = [e for e in entries if e["username"] == username]
        if action:
            entries = [e for e in entries if e["action"] == action]
        if resource_type:
            entries = [e for e in entries if e["resource_type"] == resource_type]
        for e in entries:
            rows.append({
                "timestamp": e["timestamp"],
                "username": e["username"],
                "action": e["action"],
                "resource_type": e["resource_type"],
                "resource_id": e.get("resource_id") or "",
                "details": str(e.get("details") or {}),
                "ip_address": e.get("ip_address") or "",
            })

    # Build CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["timestamp", "username", "action", "resource_type", "resource_id", "details", "ip_address"])
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit_log_{ts}.csv"'},
    )
