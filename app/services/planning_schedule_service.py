from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import date, timedelta
from typing import Any

from app.schemas.planning_schedule import PlanningScheduleRequest
from app.services.planning_schedule_llm_service import GeneratedSchedulePlan


DEFAULT_MONTE_CARLO_ITERATIONS = 5_000
DEFAULT_TASK_DURATIONS = (1, 3, 5)
POLICY_PERCENTILES = {
    "expected": 0.50,
    "recommended": 0.80,
    "conservative": 0.90,
}


class PlanningScheduleService:
    def __init__(
        self,
        *,
        monte_carlo_iterations: int = DEFAULT_MONTE_CARLO_ITERATIONS,
        random_seed: int | None = None,
    ) -> None:
        if monte_carlo_iterations < 100:
            raise ValueError("Monte Carlo 반복 횟수는 최소 100회여야 합니다.")
        self.monte_carlo_iterations = monte_carlo_iterations
        self.random_seed = random_seed

    def prepare_context(self, request: PlanningScheduleRequest) -> dict[str, Any]:
        item_by_id = {item.wbs_id: item for item in request.wbs_items}
        tasks = []
        for item in sorted(request.wbs_items, key=self._wbs_sort_key):
            if item.item_type != "TASK":
                continue
            parent = item_by_id[item.parent_wbs_id]
            phase = item_by_id[parent.parent_wbs_id]
            tasks.append({
                "wbs_id": item.wbs_id,
                "wbs_code": item.wbs_code,
                "phase_name": phase.wbs_name,
                "work_package_name": parent.wbs_name,
                "task_name": item.wbs_name,
                "description": item.description,
            })
        return {"tasks": tasks}

    def build_schedule(
        self,
        request: PlanningScheduleRequest,
        plan: GeneratedSchedulePlan,
    ) -> dict[str, Any]:
        warnings = [
            "담당자와 인력 가용성을 반영하지 않은 작업 관계 기반 일정입니다.",
            "주말만 제외하며 공휴일은 반영하지 않은 일정입니다.",
        ]
        task_items = sorted(
            (item for item in request.wbs_items if item.item_type == "TASK"),
            key=self._wbs_sort_key,
        )
        task_ids = [item.wbs_id for item in task_items]
        task_order = {task_id: index for index, task_id in enumerate(task_ids)}
        estimate_by_id = self._estimate_map(plan)

        durations_by_task: dict[int, dict[str, int]] = {}
        predecessors_by_task: dict[int, list[int]] = {}
        for task in task_items:
            estimate = estimate_by_id.get(task.wbs_id)
            if estimate is None:
                optimistic, most_likely, pessimistic = DEFAULT_TASK_DURATIONS
                proposed_predecessors: list[int] = []
                warnings.append(
                    f"{task.wbs_id} 기간 추정이 누락되어 기본 기간을 적용했습니다."
                )
            else:
                optimistic, most_likely, pessimistic = sorted((
                    estimate.optimistic_days,
                    estimate.most_likely_days,
                    estimate.pessimistic_days,
                ))
                proposed_predecessors = estimate.predecessor_wbs_ids

            durations_by_task[task.wbs_id] = self._duration_percentiles(
                request,
                task.wbs_id,
                optimistic,
                most_likely,
                pessimistic,
            )
            predecessors_by_task[task.wbs_id] = self._valid_predecessors(
                task.wbs_id,
                proposed_predecessors,
                task_order,
                warnings,
            )

        self._apply_phase_gates(
            request,
            task_items,
            predecessors_by_task,
        )

        offsets_by_policy = {
            policy: self._schedule_offsets(
                task_ids,
                predecessors_by_task,
                {
                    task_id: durations_by_task[task_id][policy]
                    for task_id in task_ids
                },
            )
            for policy in POLICY_PERCENTILES
        }
        base_date = self._next_business_day(request.project_start_date)
        ranges_by_policy = {
            policy: self._all_item_ranges(
                request,
                offsets,
                base_date,
            )
            for policy, offsets in offsets_by_policy.items()
        }

        if request.target_end_date:
            labels = {
                "expected": "예상",
                "recommended": "권장",
                "conservative": "보수적",
            }
            for policy, ranges in ranges_by_policy.items():
                project_end = max(item["end_date"] for item in ranges.values())
                if project_end > request.target_end_date:
                    warnings.append(
                        f"{labels[policy]} 일정이 목표 종료일을 초과합니다: "
                        f"{project_end.isoformat()}"
                    )

        schedules = []
        for item in request.wbs_items:
            schedules.append({
                "wbs_id": item.wbs_id,
                "expected": ranges_by_policy["expected"][item.wbs_id],
                "recommended": ranges_by_policy["recommended"][item.wbs_id],
                "conservative": ranges_by_policy["conservative"][item.wbs_id],
            })
        return {
            "project_id": request.project_id,
            "wbs_schedules": schedules,
            "warnings": self._unique(warnings),
        }

    def _estimate_map(self, plan: GeneratedSchedulePlan) -> dict[int, Any]:
        result = {}
        for estimate in plan.task_estimates:
            result.setdefault(estimate.wbs_id, estimate)
        return result

    def _duration_percentiles(
        self,
        request: PlanningScheduleRequest,
        task_id: int,
        optimistic: int,
        most_likely: int,
        pessimistic: int,
    ) -> dict[str, int]:
        seed = self._task_seed(request, task_id)
        rng = random.Random(seed)
        samples = sorted(
            max(
                1,
                round(rng.triangular(optimistic, pessimistic, most_likely)),
            )
            for _ in range(self.monte_carlo_iterations)
        )
        result = {
            policy: samples[
                min(
                    len(samples) - 1,
                    max(0, math.ceil(percentile * len(samples)) - 1),
                )
            ]
            for policy, percentile in POLICY_PERCENTILES.items()
        }
        result["recommended"] = max(result["expected"], result["recommended"])
        result["conservative"] = max(
            result["recommended"],
            result["conservative"],
        )
        return result

    def _task_seed(self, request: PlanningScheduleRequest, task_id: int) -> int:
        if self.random_seed is not None:
            seed_source = f"{self.random_seed}:{task_id}"
        else:
            request_source = {
                "project_id": request.project_id,
                "project_start_date": request.project_start_date.isoformat(),
                "target_end_date": (
                    request.target_end_date.isoformat()
                    if request.target_end_date
                    else None
                ),
                "wbs_items": [
                    {
                        "wbs_id": item.wbs_id,
                        "wbs_code": item.wbs_code,
                        "parent_wbs_id": item.parent_wbs_id,
                        "item_type": item.item_type,
                        "wbs_name": item.wbs_name,
                        "description": item.description,
                    }
                    for item in request.wbs_items
                ],
            }
            seed_source = json.dumps(
                request_source,
                ensure_ascii=False,
                sort_keys=True,
            ) + f":{task_id}"
        digest = hashlib.sha256(seed_source.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=False)

    def _valid_predecessors(
        self,
        task_id: int,
        proposed: list[int],
        task_order: dict[int, int],
        warnings: list[str],
    ) -> list[int]:
        result = []
        seen = set()
        for predecessor_id in proposed:
            if predecessor_id in seen:
                continue
            seen.add(predecessor_id)
            if predecessor_id not in task_order:
                warnings.append(
                    f"{task_id}의 존재하지 않는 선행 TASK가 제외되었습니다: "
                    f"{predecessor_id}"
                )
                continue
            if task_order[predecessor_id] >= task_order[task_id]:
                warnings.append(
                    f"{task_id}의 순서가 잘못된 선행 TASK가 제외되었습니다: "
                    f"{predecessor_id}"
                )
                continue
            result.append(predecessor_id)
        return result

    def _apply_phase_gates(
        self,
        request: PlanningScheduleRequest,
        task_items: list,
        predecessors_by_task: dict[int, list[int]],
    ) -> None:
        item_by_id = {item.wbs_id: item for item in request.wbs_items}
        phase_order = [
            item.wbs_id
            for item in sorted(request.wbs_items, key=self._wbs_sort_key)
            if item.item_type == "PHASE"
        ]
        task_phase = {}
        tasks_by_phase = {phase_id: [] for phase_id in phase_order}
        for task in task_items:
            package = item_by_id[task.parent_wbs_id]
            phase_id = package.parent_wbs_id
            task_phase[task.wbs_id] = phase_id
            tasks_by_phase[phase_id].append(task.wbs_id)

        for phase_index in range(1, len(phase_order)):
            previous_phase_id = phase_order[phase_index - 1]
            current_phase_id = phase_order[phase_index]
            previous_tasks = tasks_by_phase[previous_phase_id]
            current_tasks = tasks_by_phase[current_phase_id]
            previous_as_predecessors = {
                predecessor
                for task_id in previous_tasks
                for predecessor in predecessors_by_task[task_id]
                if task_phase.get(predecessor) == previous_phase_id
            }
            previous_terminal_tasks = [
                task_id
                for task_id in previous_tasks
                if task_id not in previous_as_predecessors
            ]
            for task_id in current_tasks:
                same_phase_predecessors = [
                    predecessor
                    for predecessor in predecessors_by_task[task_id]
                    if task_phase.get(predecessor) == current_phase_id
                ]
                if same_phase_predecessors:
                    continue
                predecessors_by_task[task_id] = self._unique([
                    *predecessors_by_task[task_id],
                    *previous_terminal_tasks,
                ])

    def _schedule_offsets(
        self,
        task_ids: list[int],
        predecessors_by_task: dict[int, list[int]],
        durations: dict[int, int],
    ) -> dict[int, tuple[int, int]]:
        result = {}
        for task_id in task_ids:
            predecessors = predecessors_by_task[task_id]
            start_offset = max(
                (result[predecessor][1] for predecessor in predecessors),
                default=0,
            )
            result[task_id] = (
                start_offset,
                start_offset + durations[task_id],
            )
        return result

    def _all_item_ranges(
        self,
        request: PlanningScheduleRequest,
        task_offsets: dict[int, tuple[int, int]],
        base_date: date,
    ) -> dict[int, dict[str, date]]:
        child_ids_by_parent: dict[int, list[int]] = {}
        for item in request.wbs_items:
            if item.parent_wbs_id:
                child_ids_by_parent.setdefault(item.parent_wbs_id, []).append(
                    item.wbs_id
                )

        descendant_cache: dict[int, list[int]] = {}

        def descendant_tasks(wbs_id: int) -> list[int]:
            if wbs_id in descendant_cache:
                return descendant_cache[wbs_id]
            if wbs_id in task_offsets:
                descendant_cache[wbs_id] = [wbs_id]
                return [wbs_id]
            task_ids = []
            for child_id in child_ids_by_parent.get(wbs_id, []):
                task_ids.extend(descendant_tasks(child_id))
            descendant_cache[wbs_id] = task_ids
            return task_ids

        max_end_offset = max(end for _, end in task_offsets.values())
        business_dates = self._business_dates(base_date, max_end_offset)
        result = {}
        for item in request.wbs_items:
            task_ids = descendant_tasks(item.wbs_id)
            start_offset = min(task_offsets[task_id][0] for task_id in task_ids)
            end_offset = max(task_offsets[task_id][1] for task_id in task_ids)
            result[item.wbs_id] = {
                "start_date": business_dates[start_offset],
                "end_date": business_dates[end_offset - 1],
            }
        return result

    def _next_business_day(self, value: date) -> date:
        while value.weekday() >= 5:
            value += timedelta(days=1)
        return value

    def _business_dates(self, start: date, count: int) -> list[date]:
        dates = []
        current = start
        while len(dates) < count:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        return dates

    def _unique(self, values: list[str]) -> list[str]:
        result = []
        seen = set()
        for value in values:
            if value not in seen:
                result.append(value)
                seen.add(value)
        return result

    def _wbs_sort_key(self, item) -> tuple:
        return tuple(
            (0, int(part)) if part.isdigit() else (1, part.lower())
            for part in item.wbs_code.split(".")
        )
