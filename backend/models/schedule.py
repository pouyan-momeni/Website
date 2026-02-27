"""Schedule ORM model — cron-based scheduled runs."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import TIMESTAMP
from sqlalchemy.orm import relationship

from backend.database import Base


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey("models.id"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    cron_expression = Column(Text, nullable=False)
    inputs = Column(JSONB, nullable=True)
    config = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    next_run_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_run_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    model = relationship("Model", back_populates="schedules")
    creator = relationship("User", back_populates="schedules", foreign_keys=[created_by])
