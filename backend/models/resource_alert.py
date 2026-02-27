"""ResourceAlert ORM model — system resource threshold alerts."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Float, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import TIMESTAMP

from backend.database import Base


class ResourceAlert(Base):
    __tablename__ = "resource_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_type = Column(Text, nullable=False)
    threshold_pct = Column(Float, nullable=False)
    triggered_at = Column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)
    notified = Column(Boolean, default=False, nullable=False)
