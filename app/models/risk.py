from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Risk(Base):
    __tablename__ = "risks"

    risk_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id"),
        nullable=False,
        index=True,
    )

    source_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("normalized_events.normalized_event_id"),
        nullable=True,
        index=True,
    )

    risk_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    risk_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    risk_title: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    risk_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    probability_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    impact_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    risk_level: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="OPEN",
        nullable=False,
    )

    detection_source: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    evidence_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    recommended_actions: Mapped[list | None] = mapped_column(
        JSON,
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