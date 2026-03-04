"""User ORM model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import TIMESTAMP
from sqlalchemy.orm import relationship

from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ldap_username = Column(Text, unique=True, nullable=False, index=True)
    email = Column(Text, nullable=True)
    role = Column(
        String(20),
        nullable=False,
        default="reader",
    )
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    runs = relationship("Run", back_populates="user")
    schedules = relationship("Schedule", back_populates="creator")
    notifications = relationship("Notification", back_populates="user")
