from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Schedule(Base):
    __tablename__ = "schedules"

    schedule_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id"),
        nullable=False,
        index=True,
    )

    wbs_id: Mapped[int] = mapped_column(
        ForeignKey("wbs.wbs_id"),
        nullable=False,
        index=True,
    )

    assignee: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    planned_start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    planned_end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="PLANNED",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )