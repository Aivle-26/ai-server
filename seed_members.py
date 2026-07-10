from datetime import date

import app.models

from app.core.database import SessionLocal
from app.models.member import (
    Member,
    MemberSkill,
    MemberWorkload,
)


db = SessionLocal()

if db.query(Member).count() == 0:

    backend = Member(
        employee_no="EMP001",
        name="김백엔드",
        primary_role="BACKEND",
        career_level="SENIOR",
    )

    frontend = Member(
        employee_no="EMP002",
        name="이프론트",
        primary_role="FRONTEND",
        career_level="MIDDLE",
    )

    ai = Member(
        employee_no="EMP003",
        name="박AI",
        primary_role="AI",
        career_level="SENIOR",
    )

    db.add_all([backend, frontend, ai])
    db.commit()

    members = db.query(Member).all()

    for member in members:

        if member.primary_role == "BACKEND":

            db.add(
                MemberSkill(
                    member_id=member.member_id,
                    skill_name="Spring Boot",
                    proficiency_level="HIGH",
                    experience_years=5,
                )
            )

            db.add(
                MemberSkill(
                    member_id=member.member_id,
                    skill_name="Python",
                    proficiency_level="HIGH",
                    experience_years=4,
                )
            )

        elif member.primary_role == "FRONTEND":

            db.add(
                MemberSkill(
                    member_id=member.member_id,
                    skill_name="React",
                    proficiency_level="HIGH",
                    experience_years=3,
                )
            )

        else:

            db.add(
                MemberSkill(
                    member_id=member.member_id,
                    skill_name="OpenAI",
                    proficiency_level="HIGH",
                    experience_years=4,
                )
            )

            db.add(
                MemberSkill(
                    member_id=member.member_id,
                    skill_name="Python",
                    proficiency_level="HIGH",
                    experience_years=5,
                )
            )

        db.add(
            MemberWorkload(
                member_id=member.member_id,
                recorded_date=date.today(),
                assigned_task_count=2,
                available_hours=30,
                workload_rate=40,
            )
        )

    db.commit()

print("팀원 데이터 생성 완료")

db.close()