from typing import Any

from sqlalchemy.orm import Session

from ..models.requirement import Requirement
from ..models.schedule import Schedule
from ..models.wbs import WBS


class RequirementImpactService:
    def evaluate(
        self,
        db: Session,
        project_id: int,
        requirement_id: int,
        change_type: str,
        change_description: str,
    ) -> dict[str, Any]:
        requirement = (
            db.query(Requirement)
            .filter(
                Requirement.project_id == project_id,
                Requirement.requirement_id == requirement_id,
            )
            .first()
        )

        if requirement is None:
            raise ValueError(
                f"requirement_id={requirement_id}인 "
                "요구사항을 찾을 수 없습니다."
            )

        related_tasks = (
            db.query(WBS)
            .filter(
                WBS.project_id == project_id,
                WBS.requirement_id == requirement_id,
            )
            .order_by(WBS.task_order)
            .all()
        )

        task_ids = [
            task.wbs_id
            for task in related_tasks
        ]

        related_schedules = []

        if task_ids:
            related_schedules = (
                db.query(Schedule)
                .filter(
                    Schedule.project_id == project_id,
                    Schedule.wbs_id.in_(task_ids),
                )
                .order_by(
                    Schedule.planned_start_date
                )
                .all()
            )

        affected_assignees = sorted(
            {
                task.assignee
                for task in related_tasks
                if task.assignee
            }
        )

        estimated_delay_days = sum(
            max(1, task.estimated_days)
            for task in related_tasks
            if task.status not in {
                "DONE",
                "COMPLETED",
                "CLOSED",
            }
        )

        impact_score = self._calculate_impact_score(
            requirement=requirement,
            change_type=change_type,
            task_count=len(related_tasks),
            schedule_count=len(related_schedules),
            assignee_count=len(affected_assignees),
            estimated_delay_days=estimated_delay_days,
        )

        impact_level = self._get_impact_level(
            impact_score
        )

        recommended_actions = (
            self._make_recommended_actions(
                change_type=change_type,
                task_count=len(related_tasks),
                schedule_count=len(
                    related_schedules
                ),
                assignee_count=len(
                    affected_assignees
                ),
                impact_level=impact_level,
            )
        )

        return {
            "project_id": project_id,
            "requirement": {
                "requirement_id":
                    requirement.requirement_id,
                "requirement_code":
                    requirement.requirement_code,
                "title":
                    requirement.title,
                "description":
                    requirement.description,
                "priority":
                    requirement.priority,
                "status":
                    requirement.status,
            },
            "change": {
                "change_type":
                    change_type.upper(),
                "change_description":
                    change_description,
            },
            "impact": {
                "impact_score":
                    impact_score,
                "impact_level":
                    impact_level,
                "affected_wbs_count":
                    len(related_tasks),
                "affected_schedule_count":
                    len(related_schedules),
                "affected_assignee_count":
                    len(affected_assignees),
                "estimated_delay_days":
                    estimated_delay_days,
            },
            "affected_wbs": [
                {
                    "wbs_id":
                        task.wbs_id,
                    "task_name":
                        task.task_name,
                    "task_order":
                        task.task_order,
                    "estimated_days":
                        task.estimated_days,
                    "assignee":
                        task.assignee,
                    "status":
                        task.status,
                }
                for task in related_tasks
            ],
            "affected_schedules": [
                {
                    "schedule_id":
                        schedule.schedule_id,
                    "wbs_id":
                        schedule.wbs_id,
                    "assignee":
                        schedule.assignee,
                    "planned_start_date":
                        schedule.planned_start_date.isoformat(),
                    "planned_end_date":
                        schedule.planned_end_date.isoformat(),
                    "status":
                        schedule.status,
                }
                for schedule in related_schedules
            ],
            "affected_assignees":
                affected_assignees,
            "requires_replanning":
                impact_level in {
                    "HIGH",
                    "CRITICAL",
                },
            "recommended_actions":
                recommended_actions,
        }

    def _calculate_impact_score(
        self,
        requirement: Requirement,
        change_type: str,
        task_count: int,
        schedule_count: int,
        assignee_count: int,
        estimated_delay_days: int,
    ) -> int:
        score = 0

        normalized_change_type = (
            change_type.strip().upper()
        )

        change_type_scores = {
            "SCOPE": 30,
            "FUNCTION": 25,
            "SCHEDULE": 20,
            "PRIORITY": 15,
            "DESCRIPTION": 10,
        }

        score += change_type_scores.get(
            normalized_change_type,
            15,
        )

        priority_scores = {
            "CRITICAL": 25,
            "HIGH": 20,
            "MEDIUM": 10,
            "LOW": 5,
        }

        score += priority_scores.get(
            str(requirement.priority).upper(),
            10,
        )

        score += min(task_count * 5, 20)
        score += min(schedule_count * 3, 15)
        score += min(assignee_count * 5, 10)
        score += min(estimated_delay_days * 2, 20)

        return min(score, 100)

    def _get_impact_level(
        self,
        score: int,
    ) -> str:
        if score >= 80:
            return "CRITICAL"

        if score >= 60:
            return "HIGH"

        if score >= 30:
            return "MEDIUM"

        return "LOW"

    def _make_recommended_actions(
        self,
        change_type: str,
        task_count: int,
        schedule_count: int,
        assignee_count: int,
        impact_level: str,
    ) -> list[str]:
        actions = []

        if task_count:
            actions.append(
                "연결된 WBS 업무의 범위와 "
                "우선순위를 재검토합니다."
            )

        if schedule_count:
            actions.append(
                "영향받는 일정의 시작일과 "
                "종료일을 재산정합니다."
            )

        if assignee_count:
            actions.append(
                "영향받는 담당자에게 변경 내용을 "
                "공유하고 업무량을 확인합니다."
            )

        if change_type.strip().upper() == "SCOPE":
            actions.append(
                "프로젝트 범위 변경에 대한 "
                "PM 승인을 진행합니다."
            )

        if impact_level in {
            "HIGH",
            "CRITICAL",
        }:
            actions.append(
                "담당자 재배정과 프로젝트 계획 "
                "재수립 여부를 검토합니다."
            )

        if not actions:
            actions.append(
                "변경 내용을 기록하고 후속 영향을 "
                "지속적으로 관찰합니다."
            )

        return list(dict.fromkeys(actions))
