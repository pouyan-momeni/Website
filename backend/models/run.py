"""Run ORM model — represents a single execution of a financial model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import TIMESTAMP
from sqlalchemy.orm import relationship

from backend.database import Base


class Run(Base):
    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey("models.id"), nullable=False, index=True)
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    status = Column(
        Text,
        nullable=False,
        default="queued",
    )
    inputs = Column(JSONB, nullable=True)
    config_snapshot = Column(JSONB, nullable=True)
    celery_task_id = Column(Text, nullable=True)
    current_container_index = Column(Integer, default=0, nullable=False)
    queue_position = Column(Integer, nullable=True)
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_archived = Column(Boolean, default=False, nullable=False)
    archived_at = Column(TIMESTAMP(timezone=True), nullable=True)
    archive_path = Column(Text, nullable=True)
    output_path = Column(Text, nullable=True)
    log_path = Column(Text, nullable=True)

    # Relationships
    model = relationship("Model", back_populates="runs")
    user = relationship("User", back_populates="runs", foreign_keys=[triggered_by])
    containers = relationship("RunContainer", back_populates="run", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="run")
