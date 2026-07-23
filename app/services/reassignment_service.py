from typing import Any

from sqlalchemy.orm import Session

from app.models.member import (
    Member,
    MemberSkill,
    MemberWorkload,
)
from app.models.schedule import Schedule
from app.models.wbs import WBS


class ReassignmentService:
    def reassign(
        self,
        db: Session,
        project_id: int,
        wbs_id: int,
        reason: str,
    ) -> dict[str, Any]:
        task = (
            db.query(WBS)
            .filter(
                WBS.project_id == project_id,
                WBS.wbs_id == wbs_id,
            )
            .first()
        )

        if task is None:
            raise ValueError(
                f"wbs_id={wbs_id}인 업무를 찾을 수 없습니다."
            )

        current_assignee = task.assignee

        required_role = self._predict_role(
            task_name=task.task_name
        )

        required_skills = self._extract_required_skills(
            task_name=task.task_name,
            task_description=task.task_description,
        )

        candidates = (
            db.query(Member)
            .filter(
                Member.primary_role == required_role,
                Member.employment_status == "ACTIVE",
            )
            .all()
        )

        candidate_results = []

        for member in candidates:
            if member.name == current_assignee:
                continue

            score_result = self._calculate_candidate_score(
                db=db,
                member=member,
                required_role=required_role,
                required_skills=required_skills,
            )

            candidate_results.append(
                score_result
            )

        if not candidate_results:
            return {
                "project_id": project_id,
                "wbs_id": task.wbs_id,
                "task_name": task.task_name,
                "previous_assignee": current_assignee,
                "new_assignee": None,
                "required_role": required_role,
                "required_skills": required_skills,
                "reassignment_status": "FAILED",
                "reason": reason,
                "message": (
                    "현재 담당자를 제외하면 "
                    "재배정 가능한 팀원이 없습니다."
                ),
                "candidates": [],
            }

        candidate_results.sort(
            key=lambda item: item["total_score"],
            reverse=True,
        )

        best_candidate = candidate_results[0]
        new_assignee = best_candidate["member_name"]

        task.assignee = new_assignee

        related_schedule = (
            db.query(Schedule)
            .filter(
                Schedule.project_id == project_id,
                Schedule.wbs_id == wbs_id,
            )
            .first()
        )

        if related_schedule:
            related_schedule.assignee = new_assignee

        try:
            db.commit()
            db.refresh(task)

            if related_schedule:
                db.refresh(related_schedule)

        except Exception:
            db.rollback()
            raise

        return {
            "project_id": project_id,
            "wbs_id": task.wbs_id,
            "task_name": task.task_name,
            "previous_assignee": current_assignee,
            "new_assignee": new_assignee,
            "required_role": required_role,
            "required_skills": required_skills,
            "reassignment_status": "COMPLETED",
            "reason": reason,
            "recommendation": {
                "member_id": best_candidate["member_id"],
                "member_name": best_candidate["member_name"],
                "total_score": best_candidate["total_score"],
                "role_score": best_candidate["role_score"],
                "skill_score": best_candidate["skill_score"],
                "proficiency_score":
                    best_candidate["proficiency_score"],
                "workload_score":
                    best_candidate["workload_score"],
                "matched_skills":
                    best_candidate["matched_skills"],
                "workload_rate":
                    best_candidate["workload_rate"],
            },
            "schedule_updated": (
                related_schedule is not None
            ),
            "candidates": candidate_results,
        }

    def _predict_role(
        self,
        task_name: str,
    ) -> str:
        text = task_name.lower()

        if any(
            keyword in text
            for keyword in [
                "react",
                "frontend",
                "front",
                "ui",
                "화면",
                "css",
            ]
        ):
            return "FRONTEND"

        if any(
            keyword in text
            for keyword in [
                "ai",
                "llm",
                "rag",
                "openai",
                "langgraph",
                "모델",
            ]
        ):
            return "AI"

        return "BACKEND"

    def _extract_required_skills(
        self,
        task_name: str,
        task_description: str | None,
    ) -> list[str]:
        text = (
            f"{task_name} "
            f"{task_description or ''}"
        ).lower()

        skill_keywords = {
            "Spring Boot": [
                "spring",
                "backend",
                "api",
                "서버",
            ],
            "Python": [
                "python",
                "ai",
                "데이터",
            ],
            "React": [
                "react",
                "frontend",
                "화면",
                "ui",
            ],
            "OpenAI": [
                "openai",
                "llm",
                "gpt",
            ],
            "LangGraph": [
                "langgraph",
                "multi agent",
                "멀티 에이전트",
            ],
            "SQL": [
                "sql",
                "db",
                "database",
                "데이터베이스",
            ],
        }

        required_skills = []

        for skill_name, keywords in (
            skill_keywords.items()
        ):
            if any(
                keyword in text
                for keyword in keywords
            ):
                required_skills.append(
                    skill_name
                )

        return required_skills

    def _calculate_candidate_score(
        self,
        db: Session,
        member: Member,
        required_role: str,
        required_skills: list[str],
    ) -> dict[str, Any]:
        role_score = (
            40
            if member.primary_role == required_role
            else 0
        )

        skills = (
            db.query(MemberSkill)
            .filter(
                MemberSkill.member_id
                == member.member_id
            )
            .all()
        )

        member_skill_names = {
            skill.skill_name.lower()
            for skill in skills
        }

        matched_skills = [
            required_skill
            for required_skill in required_skills
            if required_skill.lower()
            in member_skill_names
        ]

        if required_skills:
            skill_score = round(
                (
                    len(matched_skills)
                    / len(required_skills)
                )
                * 30
            )
        else:
            skill_score = 15

        proficiency_score = 0

        for skill in skills:
            if (
                not required_skills
                or skill.skill_name in matched_skills
            ):
                level = (
                    skill.proficiency_level.upper()
                )

                if level == "HIGH":
                    proficiency_score += 10

                elif level == "MEDIUM":
                    proficiency_score += 5

                elif level == "LOW":
                    proficiency_score += 2

        proficiency_score = min(
            proficiency_score,
            20,
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

        if workload:
            workload_rate = float(
                workload.workload_rate
            )
        else:
            workload_rate = 0.0

        workload_score = max(
            0,
            10 - int(workload_rate / 10),
        )

        total_score = (
            role_score
            + skill_score
            + proficiency_score
            + workload_score
        )

        return {
            "member_id": member.member_id,
            "member_name": member.name,
            "primary_role": member.primary_role,
            "career_level": member.career_level,
            "total_score": total_score,
            "role_score": role_score,
            "skill_score": skill_score,
            "proficiency_score":
                proficiency_score,
            "workload_score": workload_score,
            "matched_skills": matched_skills,
            "workload_rate": workload_rate,
        }