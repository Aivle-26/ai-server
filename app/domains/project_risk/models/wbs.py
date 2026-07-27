from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WBS(Base):
    __tablename__ = "wbs"

    wbs_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id"),
        nullable=False,
    )

    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("requirements.requirement_id"),
        nullable=False,
    )

    task_name: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    task_description: Mapped[str | None] = mapped_column(
        Text
    )

    task_order: Mapped[int] = mapped_column(
        Integer,
        default=1,
    )

    estimated_days: Mapped[int] = mapped_column(
        Integer,
        default=1,
    )

    assignee: Mapped[str | None] = mapped_column(
        String(100)
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="TODO",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )