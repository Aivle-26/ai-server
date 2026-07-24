from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.planning_wbs import WBSItemType


class ScheduleWBSItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    wbs_id: int = Field(gt=0)
    wbs_code: str
    parent_wbs_id: int | None = None
    item_type: WBSItemType
    wbs_name: str
    description: str


class PlanningScheduleRequest(BaseModel):
    project_id: int = Field(gt=0)
    project_start_date: date
    target_end_date: date | None = None
    wbs_items: list[ScheduleWBSItem] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_schedule_input(self) -> "PlanningScheduleRequest":
        if self.target_end_date and self.target_end_date < self.project_start_date:
            raise ValueError("목표 종료일은 프로젝트 시작일보다 빠를 수 없습니다.")

        item_by_id: dict[int, ScheduleWBSItem] = {}
        wbs_codes: set[str] = set()
        for item in self.wbs_items:
            item.wbs_code = item.wbs_code.strip()
            item.wbs_name = item.wbs_name.strip()
            item.description = item.description.strip()
            if not all((item.wbs_code, item.wbs_name, item.description)):
                raise ValueError("WBS ID, 코드, 작업명과 설명은 비어 있을 수 없습니다.")
            if item.wbs_id in item_by_id:
                raise ValueError("WBS ID는 중복될 수 없습니다.")
            if item.wbs_code in wbs_codes:
                raise ValueError("WBS 코드는 중복될 수 없습니다.")
            item_by_id[item.wbs_id] = item
            wbs_codes.add(item.wbs_code)

        task_count = sum(item.item_type == "TASK" for item in self.wbs_items)
        if task_count == 0:
            raise ValueError("일정 추천을 위해 최소 한 개의 TASK가 필요합니다.")
        if task_count > 200:
            raise ValueError("일정 추천 TASK는 최대 200개까지 허용합니다.")

        expected_parent_types = {
            "WORK_PACKAGE": "PHASE",
            "TASK": "WORK_PACKAGE",
        }
        for item in self.wbs_items:
            if item.item_type == "PHASE":
                if item.parent_wbs_id is not None:
                    raise ValueError("PHASE의 상위 WBS ID는 null이어야 합니다.")
                continue
            if not item.parent_wbs_id or item.parent_wbs_id not in item_by_id:
                raise ValueError(f"상위 WBS를 찾을 수 없습니다: {item.wbs_id}")
            parent = item_by_id[item.parent_wbs_id]
            if parent.item_type != expected_parent_types[item.item_type]:
                raise ValueError(f"WBS 계층 구조가 올바르지 않습니다: {item.wbs_id}")

        child_ids_by_parent: dict[int, list[int]] = {}
        for item in self.wbs_items:
            if item.parent_wbs_id:
                child_ids_by_parent.setdefault(item.parent_wbs_id, []).append(item.wbs_id)

        def has_task_descendant(wbs_id: int) -> bool:
            for child_id in child_ids_by_parent.get(wbs_id, []):
                child = item_by_id[child_id]
                if child.item_type == "TASK" or has_task_descendant(child_id):
                    return True
            return False

        for item in self.wbs_items:
            if item.item_type != "TASK" and not has_task_descendant(item.wbs_id):
                raise ValueError(f"하위 TASK가 없는 WBS 항목입니다: {item.wbs_id}")
        return self


class ScheduleDateRange(BaseModel):
    start_date: date
    end_date: date


class WBSScheduleRecommendation(BaseModel):
    wbs_id: int = Field(gt=0)
    expected: ScheduleDateRange
    recommended: ScheduleDateRange
    conservative: ScheduleDateRange


class PlanningScheduleResponse(BaseModel):
    project_id: int = Field(gt=0)
    wbs_schedules: list[WBSScheduleRecommendation]
    warnings: list[str] = Field(default_factory=list)
