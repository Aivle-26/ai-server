from sqlalchemy.orm import Session

from ..models.member import (
    Member,
    MemberSkill,
    MemberWorkload,
)
from ..models.wbs import WBS


class AssignmentAgent:

    def assign(
        self,
        db: Session,
        project_id: int,
    ) -> list[dict]:

        tasks = (
            db.query(WBS)
            .filter(
                WBS.project_id == project_id
            )
            .all()
        )

        assigned_results = []

        for task in tasks:

            role = self._predict_role(
                task_name=task.task_name
            )

            recommendation = self._recommend_member(
                db=db,
                role=role,
                task_name=task.task_name,
            )

            if recommendation is None:
                assigned_results.append(
                    {
                        "task": task.task_name,
                        "role": role,
                        "assignee": None,
                        "score": 0,
                        "reason": "추천 가능한 팀원이 없습니다.",
                    }
                )
                continue

            member = recommendation["member"]

            task.assignee = member.name

            assigned_results.append(
                {
                    "task": task.task_name,
                    "role": role,
                    "assignee": member.name,
                    "score": recommendation["total_score"],
                    "role_score": recommendation["role_score"],
                    "skill_score": recommendation["skill_score"],
                    "proficiency_score":
                        recommendation["proficiency_score"],
                    "workload_score":
                        recommendation["workload_score"],
                    "matched_skills":
                        recommendation["matched_skills"],
                    "workload_rate":
                        recommendation["workload_rate"],
                    "reason": recommendation["reason"],
                }
            )

        db.commit()

        return assigned_results

    def _predict_role(
        self,
        task_name: str,
    ) -> str:

        text = task_name.lower()

        if (
            "api" in text
            or "backend" in text
            or "spring" in text
            or "db" in text
            or "server" in text
        ):
            return "BACKEND"

        if (
            "react" in text
            or "ui" in text
            or "front" in text
            or "css" in text
            or "screen" in text
        ):
            return "FRONTEND"

        if (
            "ai" in text
            or "llm" in text
            or "rag" in text
            or "openai" in text
            or "vector" in text
        ):
            return "AI"

        return "BACKEND"

    def _recommend_member(
        self,
        db: Session,
        role: str,
        task_name: str,
    ) -> dict | None:

        members = (
            db.query(Member)
            .filter(
                Member.primary_role == role,
                Member.employment_status == "ACTIVE",
            )
            .all()
        )

        if not members:
            return None

        best_result = None
        best_score = -1

        task_lower = task_name.lower()

        for member in members:

            role_score = 40
            skill_score = 0
            proficiency_score = 0
            workload_score = 0
            matched_skills = []

            skills = (
                db.query(MemberSkill)
                .filter(
                    MemberSkill.member_id
                    == member.member_id
                )
                .all()
            )

            for skill in skills:

                skill_name = skill.skill_name.lower()

                if skill_name in task_lower:
                    skill_score += 30
                    matched_skills.append(
                        skill.skill_name
                    )

                if skill.proficiency_level == "HIGH":
                    proficiency_score += 10

                elif skill.proficiency_level == "MEDIUM":
                    proficiency_score += 5

            skill_score = min(
                skill_score,
                30
            )

            proficiency_score = min(
                proficiency_score,
                20
            )

            workload = (
                db.query(MemberWorkload)
                .filter(
                    MemberWorkload.member_id
                    == member.member_id
                )
                .order_by(
                    MemberWorkload.recorded_date.desc()
                )
                .first()
            )

            workload_rate = 0

            if workload:
                workload_rate = workload.workload_rate

                workload_score = max(
                    0,
                    20 - int(workload_rate / 5)
                )
            else:
                workload_score = 20

            total_score = (
                role_score
                + skill_score
                + proficiency_score
                + workload_score
            )

            reason_parts = [
                f"{role} 역할 일치",
                f"숙련도 점수 {proficiency_score}점",
                f"업무량 {workload_rate}%",
            ]

            if matched_skills:
                reason_parts.append(
                    "기술 일치: "
                    + ", ".join(matched_skills)
                )
            else:
                reason_parts.append(
                    "직접 일치 기술 없음"
                )

            result = {
                "member": member,
                "total_score": total_score,
                "role_score": role_score,
                "skill_score": skill_score,
                "proficiency_score":
                    proficiency_score,
                "workload_score": workload_score,
                "matched_skills": matched_skills,
                "workload_rate": workload_rate,
                "reason": " / ".join(reason_parts),
            }

            if total_score > best_score:
                best_score = total_score
                best_result = result

        return best_result
