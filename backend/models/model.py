"""Model ORM model — represents a financial model definition."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import TIMESTAMP
from sqlalchemy.orm import relationship

from backend.database import Base


class Model(Base):
    __tablename__ = "models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    slug = Column(Text, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(Text, nullable=True)
    docker_images = Column(JSONB, nullable=False, default=list)
    default_config = Column(JSONB, nullable=False, default=dict)
    input_schema = Column(JSONB, nullable=False, default=list)
    created_at = Column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    runs = relationship("Run", back_populates="model")
    schedules = relationship("Schedule", back_populates="model")
