"""RunContainer ORM model — tracks each Docker container in a run."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import TIMESTAMP
from sqlalchemy.orm import relationship

from backend.database import Base


class RunContainer(Base):
    __tablename__ = "run_containers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True)
    container_name = Column(Text, nullable=False)
    docker_container_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="pending")
    retry_count = Column(Integer, default=0, nullable=False)
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    exit_code = Column(Integer, nullable=True)
    log_file = Column(Text, nullable=True)

    # Relationships
    run = relationship("Run", back_populates="containers")
