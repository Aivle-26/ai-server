from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.api_types import LLMStatus, RequirementId


Priority = Literal["HIGH", "MEDIUM", "LOW", "UNSPECIFIED"]
RequirementCategory = Literal[
    "FUNCTIONAL",
    "NON_FUNCTIONAL",
    "SECURITY",
    "DATA",
    "INTERFACE",
    "OPERATION",
    "PROJECT_MANAGEMENT",
    "UNSPECIFIED",
]
ArtifactType = Literal[
    "RFP",
    "PROPOSAL",
    "REQUIREMENTS_DEFINITION",
    "FUNCTION_SPECIFICATION",
    "WBS",
    "ERD",
    "MEETING_MINUTES",
    "TEST_RESULTS",
    "WEEKLY_REPORT",
    "FINAL_REPORT",
    "UI_DESIGN",
]
RequirementChangeType = Literal["ADDED", "MODIFIED", "REMOVED", "UNCHANGED"]
RequirementReviewStatus = Literal["PENDING_REVIEW"]


class DocumentManifestItem(BaseModel):
    document_id: int = Field(gt=0)
    file_name: str = Field(min_length=1)


class NormalizedBoundingBox(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_page_bounds(self) -> "NormalizedBoundingBox":
        if self.x + self.width > 1.0 or self.y + self.height > 1.0:
            raise ValueError("bounding box must stay within the page")
        return self


class RequirementEvidence(BaseModel):
    document_id: int | None = Field(default=None, gt=0)
    source_document: str
    page_number: int | None = Field(default=None, gt=0)
    chunk_id: str
    quote_text: str = Field(min_length=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    bounding_boxes: list[NormalizedBoundingBox] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_offsets(self) -> "RequirementEvidence":
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must be provided together")
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset <= self.start_offset
        ):
            raise ValueError("end_offset must be greater than start_offset")
        return self


class RequiredArtifact(BaseModel):
    artifact_type: ArtifactType
    artifact_name: str
    required_version: str = "1.0"


class ProjectBasicInfo(BaseModel):
    project_name: str | None = None
    project_goal: str | None = None
    client_organization: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    key_features: list[str] = Field(default_factory=list)
    required_artifacts: list[RequiredArtifact] = Field(default_factory=list)
    acceptance_conditions: list[str] = Field(default_factory=list)
    budget_contract_conditions: list[str] = Field(default_factory=list)
    security_privacy_conditions: list[str] = Field(default_factory=list)


class RequirementCandidate(BaseModel):
    requirement_id: RequirementId
    function_name: str
    requirement_text: str
    category: RequirementCategory = "UNSPECIFIED"
    priority: Priority = "UNSPECIFIED"
    acceptance_criteria: str | None = None
    due_date: date | None = None
    deliverable_name: str | None = None
    security_condition: str | None = None
    source_document: str
    source_excerpt: str | None = None
    evidences: list[RequirementEvidence] = Field(default_factory=list)


class ExistingRequirement(BaseModel):
    requirement_id: RequirementId
    function_name: str
    requirement_text: str
    category: RequirementCategory = "UNSPECIFIED"
    priority: Priority = "UNSPECIFIED"
    acceptance_criteria: str | None = None
    due_date: date | None = None
    deliverable_name: str | None = None
    security_condition: str | None = None
    source_document: str
    source_excerpt: str | None = None
    evidences: list[RequirementEvidence] = Field(default_factory=list)


class RequirementChangeCandidate(BaseModel):
    candidate_id: str
    existing_requirement_id: int | None = Field(default=None, gt=0)
    change_type: RequirementChangeType
    change_reason: str
    existing_requirement: ExistingRequirement | None = None
    proposed_requirement: RequirementCandidate | None = None
    evidences: list[RequirementEvidence] = Field(default_factory=list)
    review_status: RequirementReviewStatus = "PENDING_REVIEW"


class ParsedDocumentInfo(BaseModel):
    file_name: str
    file_type: str
    character_count: int = Field(ge=0)
    processing_mode: Literal["TEXT", "PDF_VISION"]


class PlanningDocumentExtractionResponse(BaseModel):
    project_info: ProjectBasicInfo
    requirement_candidates: list[RequirementCandidate]
    documents: list[ParsedDocumentInfo]
    llm_status: LLMStatus


class PlanningRequirementReadjustmentResponse(BaseModel):
    change_candidates: list[RequirementChangeCandidate]
    documents: list[ParsedDocumentInfo]
    llm_status: LLMStatus
