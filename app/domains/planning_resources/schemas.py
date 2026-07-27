"""필요 인력·담당자·MM 추천 요청 및 응답 스키마."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AllocationStatus = Literal["PLANNED", "ACTIVE", "PAUSED", "COMPLETED"]


class ResourceWBSTask(BaseModel):
    model_config = ConfigDict(extra="ignore")

    wbs_id: int = Field(gt=0)
    wbs_name: str
    description: str
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_task(self) -> "ResourceWBSTask":
        self.wbs_name = self.wbs_name.strip()
        self.description = self.description.strip()
        if not self.wbs_name or not self.description:
            raise ValueError("WBS 작업명과 설명은 비어 있을 수 없습니다.")
        if self.end_date < self.start_date:
            raise ValueError("WBS 종료일은 시작일보다 빠를 수 없습니다.")
        return self


class MemberSkill(BaseModel):
    skill_code: str
    proficiency_level: int = Field(ge=1, le=5)
    experience_months: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def normalize_skill(self) -> "MemberSkill":
        self.skill_code = self.skill_code.strip().upper()
        if not self.skill_code:
            raise ValueError("기술 코드는 비어 있을 수 없습니다.")
        return self


class MemberAllocation(BaseModel):
    allocation_start_date: date
    allocation_end_date: date | None = None
    available_hours_per_week: float = Field(ge=0, le=168)
    allocation_status: AllocationStatus

    @model_validator(mode="after")
    def validate_allocation(self) -> "MemberAllocation":
        if (
            self.allocation_end_date
            and self.allocation_end_date < self.allocation_start_date
        ):
            raise ValueError("투입 종료일은 투입 시작일보다 빠를 수 없습니다.")
        return self


class ProjectMemberCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_member_id: int = Field(gt=0)
    roles: list[str] = Field(min_length=1, max_length=20)
    skills: list[MemberSkill] = Field(default_factory=list, max_length=100)
    allocations: list[MemberAllocation] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_member(self) -> "ProjectMemberCandidate":
        roles = []
        seen_roles = set()
        for role in self.roles:
            normalized = role.strip().upper()
            if normalized and normalized not in seen_roles:
                roles.append(normalized)
                seen_roles.add(normalized)
        if not roles:
            raise ValueError("프로젝트 역할이 한 개 이상 필요합니다.")
        self.roles = roles

        skill_codes = [skill.skill_code for skill in self.skills]
        if len(skill_codes) != len(set(skill_codes)):
            raise ValueError("한 참여자의 기술 코드는 중복될 수 없습니다.")
        return self


class PlanningResourceRequest(BaseModel):
    project_id: int = Field(gt=0)
    wbs_tasks: list[ResourceWBSTask] = Field(min_length=1, max_length=200)
    project_members: list[ProjectMemberCandidate] = Field(
        min_length=1,
        max_length=500,
    )

    @model_validator(mode="after")
    def validate_request(self) -> "PlanningResourceRequest":
        wbs_ids = [task.wbs_id for task in self.wbs_tasks]
        if len(wbs_ids) != len(set(wbs_ids)):
            raise ValueError("WBS ID는 중복될 수 없습니다.")

        member_ids = [member.project_member_id for member in self.project_members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("프로젝트 참여자 ID는 중복될 수 없습니다.")
        return self


class RequiredSkill(BaseModel):
    skill_code: str
    minimum_proficiency_level: int = Field(ge=1, le=5)


class RecommendedMember(BaseModel):
    project_member_id: int = Field(gt=0)
    recommendation_score: float = Field(ge=0, le=100)
    assigned_hours: float = Field(gt=0)
    remaining_available_hours: float = Field(ge=0)


class WBSResourceAssignment(BaseModel):
    wbs_id: int = Field(gt=0)
    required_role_code: str
    required_skills: list[RequiredSkill] = Field(default_factory=list)
    estimated_person_days: float = Field(gt=0)
    estimated_hours: float = Field(gt=0)
    estimated_mm: float = Field(gt=0)
    required_headcount: int = Field(ge=1)
    recommended_members: list[RecommendedMember] = Field(default_factory=list)
    recommendation_reason: str


class RequiredStaffing(BaseModel):
    role_code: str
    required_headcount: int = Field(ge=1)
    available_candidate_count: int = Field(ge=0)
    shortage_count: int = Field(ge=0)
    estimated_person_days: float = Field(gt=0)
    estimated_mm: float = Field(gt=0)


class PlanningResourceResponse(BaseModel):
    project_id: int = Field(gt=0)
    required_staffing: list[RequiredStaffing]
    assignments: list[WBSResourceAssignment]
    total_estimated_person_days: float = Field(gt=0)
    total_estimated_hours: float = Field(gt=0)
    total_estimated_mm: float = Field(gt=0)
    unassigned_wbs_ids: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
