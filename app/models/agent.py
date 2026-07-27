from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    agent_run_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id"),
        nullable=False
    )

    agent_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    request_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    input_reference_ids: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True
    )

    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True
    )

    model_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    prompt_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    execution_status: Mapped[str] = mapped_column(
        String(30),
        default="PENDING",
        nullable=False
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )