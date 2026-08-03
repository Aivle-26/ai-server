from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Member(Base):
    __tablename__ = "members"

    member_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    employee_no: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    primary_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    career_level: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    employment_status: Mapped[str] = mapped_column(
        String(30),
        default="ACTIVE",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


class MemberSkill(Base):
    __tablename__ = "member_skills"

    member_skill_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.member_id"),
        nullable=False,
        index=True,
    )

    skill_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    proficiency_level: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    experience_years: Mapped[float] = mapped_column(
        Float,
        default=0,
        nullable=False,
    )


class MemberWorkload(Base):
    __tablename__ = "member_workloads"

    workload_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.member_id"),
        nullable=False,
        index=True,
    )

    recorded_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    assigned_task_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    available_hours: Mapped[float] = mapped_column(
        Float,
        default=40,
        nullable=False,
    )

    workload_rate: Mapped[float] = mapped_column(
        Float,
        default=0,
        nullable=False,
    )