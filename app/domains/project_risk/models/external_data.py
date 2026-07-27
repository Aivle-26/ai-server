from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExternalRawData(Base):
    __tablename__ = "external_raw_data"

    raw_data_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id"),
        nullable=False
    )

    source_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    data_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    external_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True
    )

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False
    )

    processing_status: Mapped[str] = mapped_column(
        String(30),
        default="RECEIVED",
        nullable=False
    )

    processing_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )