from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Requirement(Base):
    __tablename__ = "requirements"

    requirement_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id"),
        nullable=False,
        index=True,
    )

    source_event_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "normalized_events.normalized_event_id"
        ),
        nullable=True,
    )

    requirement_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    requirement_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    priority: Mapped[str] = mapped_column(
        String(30),
        default="MEDIUM",
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="DRAFT",
        nullable=False,
    )

    acceptance_criteria: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )