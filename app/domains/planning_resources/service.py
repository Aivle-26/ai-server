from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

from .llm_service import GeneratedResourcePlan
from .schemas import (
    PlanningResourceRequest,
    ProjectMemberCandidate,
    ResourceWBSTask,
)


RESOURCE_TASK_BATCH_SIZE = 30
WORK_HOURS_PER_DAY = 8.0
WORKDAYS_PER_MONTH = 20.0
WORKDAYS_PER_WEEK = 5.0
ACTIVE_ALLOCATION_STATUSES = {"PLANNED", "ACTIVE"}

DEFAULT_ROLE_CODES = [
    "PROJECT_MANAGER",
    "SUB_PM",
    "TECH_LEAD",
    "PLANNER",
    "REQUIREMENT_ANALYST",
    "UI_UX_DESIGNER",
    "FRONTEND_DEVELOPER",
    "BACKEND_DEVELOPER",
    "AI_ENGINEER",
    "DATA_ENGINEER",
    "DEVOPS_ENGINEER",
    "QA_ENGINEER",
    "DOCUMENT_REVIEWER",
    "APPROVER",
]

DEFAULT_SKILL_CODES = [
    "JAVA",
    "SPRING_BOOT",
    "MYSQL",
    "REACT",
    "TYPESCRIPT",
    "PYTHON",
    "FASTAPI",
    "LANGCHAIN",
    "LANGGRAPH",
    "AWS",
    "DOCKER",
    "GITHUB_ACTIONS",
    "FIGMA",
    "PROJECT_MANAGEMENT",
    "REQUIREMENT_ANALYSIS",
]


class PlanningResourceService:
    def prepare_contexts(
        self,
        request: PlanningResourceRequest,
    ) -> list[dict[str, Any]]:
        role_codes = self._unique([
            *DEFAULT_ROLE_CODES,
            *(
                role
                for member in request.project_members
                for role in member.roles
            ),
        ])
        skill_codes = self._unique([
            *DEFAULT_SKILL_CODES,
            *(
                skill.skill_code
                for member in request.project_members
                for skill in member.skills
            ),
        ])
        tasks = [
            {
                "wbs_id": task.wbs_id,
                "wbs_name": task.wbs_name,
                "description": task.description,
            }
            for task in request.wbs_tasks
        ]
        return [
            {
                "allowed_role_codes": role_codes,
                "allowed_skill_codes": skill_codes,
                "tasks": tasks[index:index + RESOURCE_TASK_BATCH_SIZE],
            }
            for index in range(0, len(tasks), RESOURCE_TASK_BATCH_SIZE)
        ]

    def build_recommendation(
        self,
        request: PlanningResourceRequest,
        plans: list[GeneratedResourcePlan],
    ) -> dict[str, Any]:
        warnings = []
        estimates = self._estimate_map(plans)
        allowed_role_codes = {
            *DEFAULT_ROLE_CODES,
            *(
                role
                for member in request.project_members
                for role in member.roles
            ),
        }
        allowed_skill_codes = {
            *DEFAULT_SKILL_CODES,
            *(
                skill.skill_code
                for member in request.project_members
                for skill in member.skills
            ),
        }
        project_dates = self._business_days(
            min(task.start_date for task in request.wbs_tasks),
            max(task.end_date for task in request.wbs_tasks),
        )
        remaining_capacity = {
            member.project_member_id: {
                work_date: self._daily_capacity(member, work_date)
                for work_date in project_dates
            }
            for member in request.project_members
        }

        assignments = []
        assignment_details = {}
        unassigned_wbs_ids = []
        role_daily_headcount: dict[str, dict[date, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        role_person_days: dict[str, float] = defaultdict(float)
        role_has_unfilled_work: dict[str, bool] = defaultdict(bool)
        role_qualified_member_ids: dict[str, set[int]] = defaultdict(set)

        task_priority = {}
        initial_candidate_ids = {}
        for task in request.wbs_tasks:
            (
                role_code,
                required_skills,
                person_days,
                _,
                _,
                _,
            ) = self._normalize_estimate(
                estimates.get(task.wbs_id),
                allowed_role_codes,
                allowed_skill_codes,
            )
            task_dates = self._business_days(task.start_date, task.end_date)
            estimated_hours = person_days * WORK_HOURS_PER_DAY
            candidates = self._rank_candidates(
                request.project_members,
                role_code,
                required_skills,
                task_dates,
                remaining_capacity,
                estimated_hours,
            )
            candidate_capacity = sum(
                sum(
                    remaining_capacity[member_id].get(work_date, 0.0)
                    for work_date in task_dates
                )
                for _, member_id in candidates
            )
            initial_candidate_ids[task.wbs_id] = [
                member_id for _, member_id in candidates
            ]
            task_priority[task.wbs_id] = (
                len(candidates),
                candidate_capacity - estimated_hours,
                task.end_date,
                task.start_date,
                task.wbs_id,
            )

        sorted_tasks = sorted(
            request.wbs_tasks,
            key=lambda task: task_priority[task.wbs_id],
        )
        for task in sorted_tasks:
            estimate = estimates.get(task.wbs_id)
            (
                role_code,
                required_skills,
                person_days,
                estimation_reason,
                invalid_role_code,
                invalid_skill_codes,
            ) = self._normalize_estimate(
                estimate,
                allowed_role_codes,
                allowed_skill_codes,
            )
            if estimate is None:
                warnings.append(
                    f"WBS {task.wbs_id}의 공수 추정이 누락되어 기본값을 적용했습니다."
                )
            else:
                if invalid_role_code:
                    warnings.append(
                        f"WBS {task.wbs_id}에서 허용되지 않은 역할 "
                        f"{invalid_role_code}을 제외했습니다."
                    )
                if invalid_skill_codes:
                    warnings.append(
                        f"WBS {task.wbs_id}에서 허용되지 않은 기술 코드를 "
                        "제외했습니다: "
                        + ", ".join(invalid_skill_codes)
                    )

            task_dates = self._business_days(task.start_date, task.end_date)
            effective_task_days = max(1, len(task_dates))
            if not task_dates:
                warnings.append(
                    f"WBS {task.wbs_id}의 기간에 평일이 없어 담당자를 배정하지 못했습니다."
                )

            estimated_hours = person_days * WORK_HOURS_PER_DAY
            role_person_days[role_code] += person_days

            candidates = self._rank_candidates(
                request.project_members,
                role_code,
                required_skills,
                task_dates,
                remaining_capacity,
                estimated_hours,
            )
            role_qualified_member_ids[role_code].update(
                initial_candidate_ids[task.wbs_id]
            )
            required_headcount = self._required_headcount(
                candidates,
                task_dates,
                remaining_capacity,
                estimated_hours,
                effective_task_days,
            )
            for work_date in task_dates:
                role_daily_headcount[role_code][work_date] += required_headcount

            hours_left = estimated_hours
            recommended_members = []
            for score, member_id in candidates:
                if hours_left <= 0.001:
                    break
                assigned_hours = self._allocate_hours(
                    remaining_capacity[member_id],
                    task_dates,
                    hours_left,
                )
                if assigned_hours <= 0.001:
                    continue
                recommended_members.append({
                    "project_member_id": member_id,
                    "recommendation_score": round(score, 1),
                    "assigned_hours": round(assigned_hours, 1),
                })
                hours_left -= assigned_hours

            is_unassigned = hours_left > 0.01
            if is_unassigned:
                unassigned_wbs_ids.append(task.wbs_id)
                role_has_unfilled_work[role_code] = True
                warnings.append(
                    f"WBS {task.wbs_id}에 필요한 공수 {round(hours_left, 1)}시간을 "
                    "배정하지 못했습니다."
                )

            assignment_details[task.wbs_id] = {
                "task_dates": task_dates,
                "recommended_members": recommended_members,
            }
            if recommended_members:
                recommendation_reason = (
                    f"{estimation_reason} 역할·기술·경력과 TASK 기간의 가용시간을 "
                    f"비교해 {len(recommended_members)}명을 추천했습니다."
                )
            else:
                recommendation_reason = (
                    f"{estimation_reason} 역할·기술·가용시간을 모두 충족하는 "
                    "프로젝트 참여자를 찾지 못했습니다."
                )

            assignments.append({
                "wbs_id": task.wbs_id,
                "required_role_code": role_code,
                "required_skills": required_skills,
                "estimated_person_days": self._round(person_days),
                "estimated_hours": self._round(estimated_hours),
                "estimated_mm": self._round(person_days / WORKDAYS_PER_MONTH),
                "required_headcount": required_headcount,
                "recommended_members": recommended_members,
                "recommendation_reason": recommendation_reason,
            })

        for assignment in assignments:
            details = assignment_details[assignment["wbs_id"]]
            for recommended in assignment["recommended_members"]:
                member_id = recommended["project_member_id"]
                recommended["remaining_available_hours"] = self._round(sum(
                    remaining_capacity[member_id].get(work_date, 0.0)
                    for work_date in details["task_dates"]
                ))

        required_staffing = []
        for role_code in sorted(role_person_days):
            required_headcount = max(
                1,
                max(
                    role_daily_headcount[role_code].values(),
                    default=0,
                ),
            )
            available_candidate_count = len(
                role_qualified_member_ids[role_code]
            )
            shortage_count = max(
                0,
                required_headcount - available_candidate_count,
            )
            if role_has_unfilled_work[role_code] and shortage_count == 0:
                shortage_count = 1
            if shortage_count:
                warnings.append(
                    f"{role_code} 역할 인력이 {shortage_count}명 부족합니다."
                )
            person_days = role_person_days[role_code]
            required_staffing.append({
                "role_code": role_code,
                "required_headcount": required_headcount,
                "available_candidate_count": available_candidate_count,
                "shortage_count": shortage_count,
                "estimated_person_days": self._round(person_days),
                "estimated_mm": self._round(
                    person_days / WORKDAYS_PER_MONTH
                ),
            })

        assignment_order = {
            task.wbs_id: index
            for index, task in enumerate(request.wbs_tasks)
        }
        assignments.sort(key=lambda item: assignment_order[item["wbs_id"]])
        total_person_days = sum(role_person_days.values())
        return {
            "project_id": request.project_id,
            "required_staffing": required_staffing,
            "assignments": assignments,
            "total_estimated_person_days": self._round(total_person_days),
            "total_estimated_hours": self._round(
                total_person_days * WORK_HOURS_PER_DAY
            ),
            "total_estimated_mm": self._round(
                total_person_days / WORKDAYS_PER_MONTH
            ),
            "unassigned_wbs_ids": unassigned_wbs_ids,
            "warnings": self._unique(warnings),
        }

    def _estimate_map(
        self,
        plans: list[GeneratedResourcePlan],
    ) -> dict[int, Any]:
        result = {}
        for plan in plans:
            for estimate in plan.task_estimates:
                result.setdefault(estimate.wbs_id, estimate)
        return result

    def _normalize_estimate(
        self,
        estimate: Any,
        allowed_role_codes: set[str],
        allowed_skill_codes: set[str],
    ) -> tuple[str, list[dict[str, Any]], float, str, str | None, list[str]]:
        if estimate is None:
            return (
                "UNSPECIFIED",
                [],
                1.0,
                "LLM 공수 추정이 누락되어 기본 공수 1인일을 적용했습니다.",
                None,
                [],
            )

        proposed_role_code = estimate.required_role_code.strip().upper()
        invalid_role_code = None
        if proposed_role_code in allowed_role_codes:
            role_code = proposed_role_code
        else:
            role_code = "UNSPECIFIED"
            invalid_role_code = proposed_role_code

        proposed_skills = self._required_skills(
            estimate.required_skills
        )
        invalid_skill_codes = [
            skill["skill_code"]
            for skill in proposed_skills
            if skill["skill_code"] not in allowed_skill_codes
        ]
        required_skills = [
            skill
            for skill in proposed_skills
            if skill["skill_code"] in allowed_skill_codes
        ]
        return (
            role_code,
            required_skills,
            float(estimate.estimated_person_days),
            estimate.estimation_reason.strip(),
            invalid_role_code,
            invalid_skill_codes,
        )

    def _required_skills(self, skills: Iterable[Any]) -> list[dict[str, Any]]:
        result = []
        seen = set()
        for skill in skills:
            code = skill.skill_code.strip().upper()
            if not code or code in seen:
                continue
            result.append({
                "skill_code": code,
                "minimum_proficiency_level": skill.minimum_proficiency_level,
            })
            seen.add(code)
        return result

    def _rank_candidates(
        self,
        members: list[ProjectMemberCandidate],
        role_code: str,
        required_skills: list[dict[str, Any]],
        task_dates: list[date],
        remaining_capacity: dict[int, dict[date, float]],
        estimated_hours: float,
    ) -> list[tuple[float, int]]:
        candidates = []
        for member in members:
            if role_code not in member.roles:
                continue
            skill_by_code = {
                skill.skill_code: skill
                for skill in member.skills
            }
            if any(
                (
                    required["skill_code"] not in skill_by_code
                    or skill_by_code[
                        required["skill_code"]
                    ].proficiency_level
                    < required["minimum_proficiency_level"]
                )
                for required in required_skills
            ):
                continue

            available_hours = sum(
                remaining_capacity[member.project_member_id].get(
                    work_date,
                    0.0,
                )
                for work_date in task_dates
            )
            if available_hours <= 0:
                continue

            if required_skills:
                proficiency_score = 30.0 * sum(
                    skill_by_code[
                        required["skill_code"]
                    ].proficiency_level / 5.0
                    for required in required_skills
                ) / len(required_skills)
                experience_score = 15.0 * sum(
                    min(
                        1.0,
                        (
                            skill_by_code[
                                required["skill_code"]
                            ].experience_months
                            or 0
                        ) / 60.0,
                    )
                    for required in required_skills
                ) / len(required_skills)
            else:
                proficiency_score = 30.0
                experience_score = 0.0

            availability_score = 20.0 * min(
                1.0,
                available_hours / estimated_hours,
            )
            score = (
                35.0
                + proficiency_score
                + experience_score
                + availability_score
            )
            candidates.append((
                round(score, 4),
                member.project_member_id,
            ))

        candidates.sort(key=lambda item: (-item[0], item[1]))
        return candidates

    def _allocate_hours(
        self,
        member_capacity: dict[date, float],
        task_dates: list[date],
        requested_hours: float,
    ) -> float:
        hours_left = requested_hours
        assigned = 0.0
        for work_date in task_dates:
            if hours_left <= 0.001:
                break
            available = member_capacity.get(work_date, 0.0)
            used = min(available, hours_left)
            member_capacity[work_date] = max(0.0, available - used)
            assigned += used
            hours_left -= used
        return assigned

    def _required_headcount(
        self,
        candidates: list[tuple[float, int]],
        task_dates: list[date],
        remaining_capacity: dict[int, dict[date, float]],
        estimated_hours: float,
        effective_task_days: int,
    ) -> int:
        capacities = sorted(
            (
                sum(
                    remaining_capacity[member_id].get(work_date, 0.0)
                    for work_date in task_dates
                )
                for _, member_id in candidates
            ),
            reverse=True,
        )
        covered_hours = 0.0
        for index, capacity in enumerate(capacities, start=1):
            covered_hours += capacity
            if covered_hours + 0.001 >= estimated_hours:
                return index

        missing_hours = max(0.0, estimated_hours - covered_hours)
        full_time_capacity = max(
            WORK_HOURS_PER_DAY,
            effective_task_days * WORK_HOURS_PER_DAY,
        )
        additional_people = math.ceil(missing_hours / full_time_capacity)
        return max(1, len(capacities) + additional_people)

    def _daily_capacity(
        self,
        member: ProjectMemberCandidate,
        work_date: date,
    ) -> float:
        matching_hours = [
            allocation.available_hours_per_week / WORKDAYS_PER_WEEK
            for allocation in member.allocations
            if (
                allocation.allocation_status in ACTIVE_ALLOCATION_STATUSES
                and allocation.allocation_start_date <= work_date
                and (
                    allocation.allocation_end_date is None
                    or work_date <= allocation.allocation_end_date
                )
            )
        ]
        return max(matching_hours, default=0.0)

    def _business_days(self, start: date, end: date) -> list[date]:
        result = []
        current = start
        while current <= end:
            if current.weekday() < 5:
                result.append(current)
            current += timedelta(days=1)
        return result

    def _unique(self, values: Iterable[str]) -> list[str]:
        result = []
        seen = set()
        for value in values:
            if value not in seen:
                result.append(value)
                seen.add(value)
        return result

    def _round(self, value: float) -> float:
        return round(value + 1e-10, 2)
