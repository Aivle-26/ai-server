from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .llm_service import GeneratedWBSPlan
from .schemas import WBSGenerationRequest


WBS_REQUIREMENT_BATCH_SIZE = 30


@dataclass(frozen=True)
class WBSBuildOutcome:
    result: dict[str, Any]
    missing_requirement_ids: list[int]
    missing_artifact_types: list[str]
    missing_phase_names: list[str]

    @property
    def needs_repair(self) -> bool:
        return bool(
            self.missing_requirement_ids
            or self.missing_artifact_types
            or self.missing_phase_names
        )


class PlanningWBSService:
    def prepare_contexts(
        self,
        request: WBSGenerationRequest,
        *,
        target_requirement_ids: list[int] | None = None,
        target_artifact_types: list[str] | None = None,
        target_phase_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        requirements = request.requirement_candidates
        if target_requirement_ids:
            targets = set(target_requirement_ids)
            requirements = [item for item in requirements if item.requirement_id in targets]

        requirements = sorted(
            requirements,
            key=lambda item: (item.category, item.function_name, item.requirement_id),
        )
        compact_requirements = [
            {
                "requirement_id": item.requirement_id,
                "function_name": item.function_name,
                "requirement_text": item.requirement_text,
                "category": item.category,
                "priority": item.priority,
                "acceptance_criteria": item.acceptance_criteria,
                "deliverable_name": item.deliverable_name,
                "security_condition": item.security_condition,
            }
            for item in requirements
        ]

        artifacts = request.project_info.required_artifacts
        if target_artifact_types:
            artifact_targets = set(target_artifact_types)
            artifacts = [item for item in artifacts if item.artifact_type in artifact_targets]

        base_context = {
            "generation_mode": "REPAIR" if any((
                target_requirement_ids,
                target_artifact_types,
                target_phase_names,
            )) else "INITIAL",
            "project": {
                "project_name": request.project_info.project_name,
                "project_goal": request.project_info.project_goal,
                "key_features": request.project_info.key_features,
                "acceptance_conditions": request.project_info.acceptance_conditions,
                "security_privacy_conditions": request.project_info.security_privacy_conditions,
                "required_artifacts": [
                    item.model_dump(mode="json") for item in artifacts
                ],
            },
            "methodology": request.methodology,
            "target_phase_names": target_phase_names or [],
        }

        if not compact_requirements:
            return [{**base_context, "requirements": []}]

        return [
            {
                **base_context,
                "requirements": compact_requirements[index:index + WBS_REQUIREMENT_BATCH_SIZE],
            }
            for index in range(0, len(compact_requirements), WBS_REQUIREMENT_BATCH_SIZE)
        ]

    def finalize(
        self,
        request: WBSGenerationRequest,
        plans: list[GeneratedWBSPlan],
        extra_warnings: Iterable[str] = (),
    ) -> WBSBuildOutcome:
        warnings = list(extra_warnings)
        requirement_order = {
            item.requirement_id: index
            for index, item in enumerate(request.requirement_candidates)
        }
        valid_requirement_ids = set(requirement_order)

        artifact_by_type = {}
        artifact_order = {}
        for artifact in request.project_info.required_artifacts:
            if artifact.artifact_type not in artifact_by_type:
                artifact_order[artifact.artifact_type] = len(artifact_order)
                artifact_by_type[artifact.artifact_type] = artifact
        valid_artifact_types = set(artifact_by_type)

        phase_by_key = {
            self._key(stage): {
                "name": stage,
                "description": "",
                "completion_criteria": [],
                "work_packages": {},
            }
            for stage in request.methodology
        }

        for plan in plans:
            plan_data = self._to_dict(plan)
            for phase in plan_data.get("phases") or []:
                phase_key = self._key(phase.get("phase_name"))
                phase_bucket = phase_by_key.get(phase_key)
                if phase_bucket is None:
                    phase_name = self._clean(phase.get("phase_name")) or "이름 없는 단계"
                    warnings.append(f"방법론에 없는 단계가 제외되었습니다: {phase_name}")
                    continue

                if not phase_bucket["description"]:
                    phase_bucket["description"] = self._clean(phase.get("description"))
                phase_bucket["completion_criteria"] = self._merge_strings(
                    phase_bucket["completion_criteria"],
                    phase.get("completion_criteria") or [],
                )

                for work_package in phase.get("work_packages") or []:
                    package_name = self._clean(work_package.get("name"))
                    if not package_name:
                        warnings.append(f"{phase_bucket['name']} 단계의 이름 없는 작업 묶음이 제외되었습니다.")
                        continue
                    package_key = self._key(package_name)
                    package_bucket = phase_bucket["work_packages"].setdefault(package_key, {
                        "name": package_name,
                        "description": self._clean(work_package.get("description")),
                        "completion_criteria": [],
                        "tasks": {},
                    })
                    package_bucket["completion_criteria"] = self._merge_strings(
                        package_bucket["completion_criteria"],
                        work_package.get("completion_criteria") or [],
                    )

                    for task in work_package.get("tasks") or []:
                        task_name = self._clean(task.get("name"))
                        if not task_name:
                            warnings.append(f"{package_name}의 이름 없는 작업이 제외되었습니다.")
                            continue
                        task_key = self._key(task_name)
                        task_bucket = package_bucket["tasks"].setdefault(task_key, {
                            "name": task_name,
                            "description": self._clean(task.get("description")),
                            "mapped_requirement_ids": [],
                            "related_artifact_types": [],
                            "completion_criteria": [],
                        })

                        proposed_requirement_ids = self._clean_ids(
                            task.get("mapped_requirement_ids") or []
                        )
                        invalid_requirement_ids = [
                            item for item in proposed_requirement_ids
                            if item not in valid_requirement_ids
                        ]
                        if invalid_requirement_ids:
                            warnings.append(
                                f"{task_name}에서 존재하지 않는 요구사항 ID가 제외되었습니다: "
                                + ", ".join(map(str, invalid_requirement_ids))
                            )
                        task_bucket["mapped_requirement_ids"] = self._merge_ids(
                            task_bucket["mapped_requirement_ids"],
                            [
                                item for item in proposed_requirement_ids
                                if item in valid_requirement_ids
                            ],
                        )

                        proposed_artifact_types = self._clean_list(
                            task.get("related_artifact_types") or []
                        )
                        unavailable_artifact_types = [
                            item for item in proposed_artifact_types
                            if item not in valid_artifact_types
                        ]
                        if unavailable_artifact_types:
                            warnings.append(
                                f"{task_name}에서 필수 산출물이 아닌 유형이 제외되었습니다: "
                                + ", ".join(unavailable_artifact_types)
                            )
                        task_bucket["related_artifact_types"] = self._merge_strings(
                            task_bucket["related_artifact_types"],
                            [
                                item for item in proposed_artifact_types
                                if item in valid_artifact_types
                            ],
                        )
                        task_bucket["completion_criteria"] = self._merge_strings(
                            task_bucket["completion_criteria"],
                            task.get("completion_criteria") or [],
                        )

        items = []
        mapped_leaf_requirements = set()
        mapped_leaf_artifacts = set()
        missing_phase_names = []
        sequence = 0

        def next_wbs_id() -> int:
            nonlocal sequence
            sequence += 1
            return sequence

        for phase_index, stage in enumerate(request.methodology, start=1):
            phase_bucket = phase_by_key[self._key(stage)]
            packages = [
                package for package in phase_bucket["work_packages"].values()
                if package["tasks"]
            ]
            if not packages:
                missing_phase_names.append(stage)
                warnings.append(f"{stage} 단계에 수행 가능한 TASK가 없습니다.")

            phase_requirement_ids = self._ordered_requirements(
                self._task_values(packages, "mapped_requirement_ids"),
                requirement_order,
            )
            phase_artifact_types = self._ordered_artifacts(
                self._task_values(packages, "related_artifact_types"),
                artifact_order,
            )
            phase_id = next_wbs_id()
            items.append({
                "wbs_id": phase_id,
                "wbs_code": str(phase_index),
                "parent_wbs_id": None,
                "level": 1,
                "sort_order": phase_index,
                "item_type": "PHASE",
                "wbs_name": stage,
                "description": phase_bucket["description"] or f"{stage} 단계 작업 수행",
                "mapped_requirement_ids": phase_requirement_ids,
                "related_artifacts": self._artifact_objects(
                    phase_artifact_types, artifact_by_type
                ),
                "completion_criteria": phase_bucket["completion_criteria"]
                or [f"{stage} 단계 작업 완료"],
            })

            for package_index, package in enumerate(packages, start=1):
                tasks = list(package["tasks"].values())
                package_requirement_ids = self._ordered_requirements(
                    self._task_values([package], "mapped_requirement_ids"),
                    requirement_order,
                )
                package_artifact_types = self._ordered_artifacts(
                    self._task_values([package], "related_artifact_types"),
                    artifact_order,
                )
                package_id = next_wbs_id()
                items.append({
                    "wbs_id": package_id,
                    "wbs_code": f"{phase_index}.{package_index}",
                    "parent_wbs_id": phase_id,
                    "level": 2,
                    "sort_order": package_index,
                    "item_type": "WORK_PACKAGE",
                    "wbs_name": package["name"],
                    "description": package["description"] or f"{package['name']} 작업 수행",
                    "mapped_requirement_ids": package_requirement_ids,
                    "related_artifacts": self._artifact_objects(
                        package_artifact_types, artifact_by_type
                    ),
                    "completion_criteria": package["completion_criteria"]
                    or [f"{package['name']} 작업 완료"],
                })

                for task_index, task in enumerate(tasks, start=1):
                    requirement_ids = self._ordered_requirements(
                        task["mapped_requirement_ids"], requirement_order
                    )
                    artifact_types = self._ordered_artifacts(
                        task["related_artifact_types"], artifact_order
                    )
                    mapped_leaf_requirements.update(requirement_ids)
                    mapped_leaf_artifacts.update(artifact_types)
                    items.append({
                        "wbs_id": next_wbs_id(),
                        "wbs_code": f"{phase_index}.{package_index}.{task_index}",
                        "parent_wbs_id": package_id,
                        "level": 3,
                        "sort_order": task_index,
                        "item_type": "TASK",
                        "wbs_name": task["name"],
                        "description": task["description"] or task["name"],
                        "mapped_requirement_ids": requirement_ids,
                        "related_artifacts": self._artifact_objects(
                            artifact_types, artifact_by_type
                        ),
                        "completion_criteria": task["completion_criteria"],
                    })

        missing_requirement_ids = [
            item.requirement_id for item in request.requirement_candidates
            if item.requirement_id not in mapped_leaf_requirements
        ]
        missing_artifact_types = [
            artifact_type for artifact_type in artifact_by_type
            if artifact_type not in mapped_leaf_artifacts
        ]
        if missing_requirement_ids:
            warnings.append(
                "WBS TASK에 연결되지 않은 요구사항이 있습니다: "
                + ", ".join(map(str, missing_requirement_ids))
            )
        if missing_artifact_types:
            warnings.append(
                "WBS TASK에 연결되지 않은 필수 산출물이 있습니다: "
                + ", ".join(missing_artifact_types)
            )

        total_requirements = len(request.requirement_candidates)
        mapped_requirements = total_requirements - len(missing_requirement_ids)
        total_artifacts = len(artifact_by_type)
        mapped_artifacts = total_artifacts - len(missing_artifact_types)
        is_partial = bool(
            missing_requirement_ids or missing_artifact_types or missing_phase_names
        )
        result = {
            "project_name": request.project_info.project_name,
            "methodology": request.methodology,
            "wbs_items": items,
            "requirement_coverage": {
                "total_requirements": total_requirements,
                "mapped_requirements": mapped_requirements,
                "unmapped_requirement_ids": missing_requirement_ids,
                "coverage_rate": self._coverage_rate(mapped_requirements, total_requirements),
            },
            "artifact_coverage": {
                "total_required_artifacts": total_artifacts,
                "mapped_artifacts": mapped_artifacts,
                "unmapped_artifact_types": missing_artifact_types,
                "coverage_rate": self._coverage_rate(mapped_artifacts, total_artifacts),
            },
            "warnings": self._clean_list(warnings),
            "generation_status": "PARTIAL" if is_partial else "SUCCEEDED",
        }
        return WBSBuildOutcome(
            result=result,
            missing_requirement_ids=missing_requirement_ids,
            missing_artifact_types=missing_artifact_types,
            missing_phase_names=missing_phase_names,
        )

    def _task_values(self, packages: list[dict[str, Any]], field: str) -> list[Any]:
        values = []
        for package in packages:
            for task in package["tasks"].values():
                values.extend(task[field])
        return values

    def _artifact_objects(self, artifact_types: list[str], artifact_by_type: dict) -> list[dict]:
        return [artifact_by_type[item].model_dump(mode="json") for item in artifact_types]

    def _ordered_requirements(self, values: Iterable[int], order: dict[int, int]) -> list[int]:
        return sorted(set(values), key=lambda item: order[item])

    def _ordered_artifacts(self, values: Iterable[str], order: dict[str, int]) -> list[str]:
        return sorted(set(values), key=lambda item: order[item])

    def _coverage_rate(self, mapped: int, total: int) -> float:
        return 100.0 if total == 0 else round(mapped / total * 100, 1)

    def _to_dict(self, value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return dict(value)

    def _key(self, value: Any) -> str:
        return "".join(self._clean(value).lower().split())

    def _clean(self, value: Any) -> str:
        return " ".join(str(value or "").split()).strip()

    def _clean_list(self, values: Iterable[Any]) -> list[str]:
        return self._merge_strings([], values)

    def _clean_ids(self, values: Iterable[Any]) -> list[int]:
        return self._merge_ids([], values)

    def _merge_ids(self, existing: list[int], new_values: Iterable[Any]) -> list[int]:
        result = list(existing)
        seen = set(result)
        for value in new_values:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0 and parsed not in seen:
                result.append(parsed)
                seen.add(parsed)
        return result

    def _merge_strings(self, existing: list[str], new_values: Iterable[Any]) -> list[str]:
        result = list(existing)
        seen = set(result)
        for value in new_values:
            cleaned = self._clean(value)
            if cleaned and cleaned not in seen:
                result.append(cleaned)
                seen.add(cleaned)
        return result
