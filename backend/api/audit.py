"""Audit Log API routes — captures user actions across the platform."""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.auth.dependencies import get_current_user
from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])

# ─── In-memory audit log store (dev mode) ─────────────────────────────────
_AUDIT_LOG: list[dict] = []
_MAX_AUDIT_ENTRIES = 500  # Keep last 500 entries in memory


class AuditEntry(BaseModel):
    id: str
    timestamp: str
    user_id: str
    username: str
    action: str         # e.g. "login", "create_run", "schedule_run", "start_notebook"
    resource_type: str  # e.g. "auth", "run", "schedule", "notebook", "model"
    resource_id: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    ip_address: Optional[str] = None


def log_action(
    username: str,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
):
    """Record an audit log entry. Called from other API modules."""
    entry = {
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
    _AUDIT_LOG.insert(0, entry)  # newest first

    # Trim to max size
    if len(_AUDIT_LOG) > _MAX_AUDIT_ENTRIES:
        _AUDIT_LOG[:] = _AUDIT_LOG[:_MAX_AUDIT_ENTRIES]

    logger.info("AUDIT: user=%s action=%s resource=%s/%s", username, action, resource_type, resource_id or "-")


@router.get("")
async def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    username: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
):
    """Get audit log entries. Admin only in production, all roles in dev."""
    entries = list(_AUDIT_LOG)

    # Filters
    if username:
        entries = [e for e in entries if e["username"] == username]
    if action:
        entries = [e for e in entries if e["action"] == action]
    if resource_type:
        entries = [e for e in entries if e["resource_type"] == resource_type]

    total = len(entries)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "entries": entries[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
