from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NormalizedEvent(Base):
    __tablename__ = "normalized_events"

    normalized_event_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id"),
        nullable=False
    )

    raw_data_id: Mapped[int] = mapped_column(
        ForeignKey("external_raw_data.raw_data_id"),
        nullable=False
    )

    source_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    priority: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    actor_external_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True
    )

    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )