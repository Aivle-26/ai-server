from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.planning_document import ProjectBasicInfo, RequiredArtifact, RequirementCandidate


DEFAULT_METHODOLOGY = ["요구사항 분석", "설계", "개발", "테스트", "검수"]
WBSItemType = Literal["PHASE", "WORK_PACKAGE", "TASK"]
WBSGenerationStatus = Literal["SUCCEEDED", "PARTIAL"]


class WBSGenerationRequest(BaseModel):
    project_info: ProjectBasicInfo
    requirement_candidates: list[RequirementCandidate] = Field(min_length=1, max_length=200)
    methodology: list[str] = Field(
        default_factory=lambda: list(DEFAULT_METHODOLOGY),
        min_length=1,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_wbs_input(self) -> "WBSGenerationRequest":
        if not (self.project_info.project_name or "").strip():
            raise ValueError("프로젝트명이 필요합니다.")

        requirement_ids = [item.requirement_id.strip() for item in self.requirement_candidates]
        if any(not requirement_id for requirement_id in requirement_ids):
            raise ValueError("요구사항 ID는 비어 있을 수 없습니다.")
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("요구사항 ID는 중복될 수 없습니다.")
        for item, requirement_id in zip(
            self.requirement_candidates,
            requirement_ids,
            strict=True,
        ):
            item.requirement_id = requirement_id

        methodology = [stage.strip() for stage in self.methodology if stage.strip()]
        if not methodology:
            raise ValueError("방법론 단계가 최소 한 개 필요합니다.")
        if len(methodology) != len(set(methodology)):
            raise ValueError("방법론 단계는 중복될 수 없습니다.")
        self.project_info.project_name = self.project_info.project_name.strip()
        self.methodology = methodology
        return self


class WBSItem(BaseModel):
    wbs_id: str
    wbs_code: str
    parent_wbs_id: str | None = None
    level: Literal[1, 2, 3]
    sort_order: int = Field(ge=1)
    item_type: WBSItemType
    wbs_name: str
    description: str
    mapped_requirement_ids: list[str] = Field(default_factory=list)
    related_artifacts: list[RequiredArtifact] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)


class RequirementCoverage(BaseModel):
    total_requirements: int = Field(ge=0)
    mapped_requirements: int = Field(ge=0)
    unmapped_requirement_ids: list[str] = Field(default_factory=list)
    coverage_rate: float = Field(ge=0, le=100)


class ArtifactCoverage(BaseModel):
    total_required_artifacts: int = Field(ge=0)
    mapped_artifacts: int = Field(ge=0)
    unmapped_artifact_types: list[str] = Field(default_factory=list)
    coverage_rate: float = Field(ge=0, le=100)


class WBSGenerationResponse(BaseModel):
    project_name: str
    methodology: list[str]
    wbs_items: list[WBSItem]
    requirement_coverage: RequirementCoverage
    artifact_coverage: ArtifactCoverage
    warnings: list[str] = Field(default_factory=list)
    generation_status: WBSGenerationStatus
