"""KOSA 직무별 공수를 검증·집계하고 MM으로 변환한다."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .effort_llm_service import GeneratedEffortPlan
from .effort_schemas import (
    DETAILED_JOB_CATEGORY,
    KosaDetailedJob,
    PlanningEffortEstimateRequest,
)


WORKDAYS_PER_MONTH = Decimal("20.5")
EFFORT_PRECISION = Decimal("0.01")


class InvalidEffortLLMResponseError(RuntimeError):
    pass


class PlanningEffortService:
    def prepare_context(self, request: PlanningEffortEstimateRequest) -> dict:
        return {
            "project_id": request.project_id,
            "project_name": request.project_name,
            "wbs_tasks": [
                {
                    "wbs_id": task.wbs_id,
                    "wbs_name": task.wbs_name,
                    "description": task.description,
                    "start_date": (
                        task.start_date.isoformat() if task.start_date else None
                    ),
                    "end_date": task.end_date.isoformat() if task.end_date else None,
                }
                for task in request.wbs_tasks
            ],
        }

    def build_response(
        self,
        request: PlanningEffortEstimateRequest,
        generated: GeneratedEffortPlan,
    ) -> dict[str, Any]:
        task_by_id = {task.wbs_id: task for task in request.wbs_tasks}
        generated_by_id = {}
        for effort in generated.wbs_efforts:
            if effort.wbs_id not in task_by_id:
                raise InvalidEffortLLMResponseError(
                    f"AI 응답에 요청하지 않은 WBS ID가 포함되어 있습니다: {effort.wbs_id}"
                )
            if effort.wbs_id in generated_by_id:
                raise InvalidEffortLLMResponseError(
                    f"AI 응답의 WBS ID가 중복되었습니다: {effort.wbs_id}"
                )
            generated_by_id[effort.wbs_id] = effort

        missing_ids = set(task_by_id) - set(generated_by_id)
        if missing_ids:
            missing = ", ".join(str(item) for item in sorted(missing_ids))
            raise InvalidEffortLLMResponseError(
                f"AI 응답에 WBS 공수 결과가 누락되었습니다: {missing}"
            )

        role_days: dict[KosaDetailedJob, Decimal] = defaultdict(Decimal)
        role_wbs_ids: dict[KosaDetailedJob, list[int]] = defaultdict(list)
        wbs_efforts = []
        total_days = Decimal("0")

        for task in request.wbs_tasks:
            generated_effort = generated_by_id[task.wbs_id]
            person_days = Decimal(str(generated_effort.estimated_person_days))
            detailed_job = generated_effort.detailed_job
            category = DETAILED_JOB_CATEGORY[detailed_job]
            role_days[detailed_job] += person_days
            role_wbs_ids[detailed_job].append(task.wbs_id)
            total_days += person_days
            wbs_efforts.append({
                "wbs_id": task.wbs_id,
                "wbs_name": task.wbs_name,
                "kosa_job_category": category.value,
                "detailed_job": detailed_job.value,
                "estimated_person_days": self._round(person_days),
                "estimated_mm": self._mm(person_days),
                "estimation_reason": generated_effort.estimation_reason.strip(),
                "confidence": round(generated_effort.confidence, 2),
            })

        job_efforts = [
            {
                "kosa_job_category": DETAILED_JOB_CATEGORY[detailed_job].value,
                "detailed_job": detailed_job.value,
                "estimated_person_days": self._round(role_days[detailed_job]),
                "estimated_mm": self._mm(role_days[detailed_job]),
                "wbs_ids": role_wbs_ids[detailed_job],
            }
            for detailed_job in KosaDetailedJob
            if detailed_job in role_days
        ]
        return {
            "project_id": request.project_id,
            "workdays_per_month": float(WORKDAYS_PER_MONTH),
            "wbs_efforts": wbs_efforts,
            "job_efforts": job_efforts,
            "total_estimated_person_days": self._round(total_days),
            "total_estimated_mm": self._mm(total_days),
            "llm_status": "SUCCEEDED",
        }

    def _round(self, value: Decimal) -> float:
        return float(value.quantize(EFFORT_PRECISION, rounding=ROUND_HALF_UP))

    def _mm(self, person_days: Decimal) -> float:
        return self._round(person_days / WORKDAYS_PER_MONTH)
