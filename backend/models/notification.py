"""Notification ORM model — email notifications sent for run events."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import TIMESTAMP
from sqlalchemy.orm import relationship

from backend.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True)
    event = Column(
        Text,
        nullable=False,
    )
    sent_at = Column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    success = Column(Boolean, default=True, nullable=False)

    # Relationships
    user = relationship("User", back_populates="notifications")
    run = relationship("Run", back_populates="notifications")
