from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


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
LLMStatus = Literal["SUCCEEDED", "SKIPPED_NO_API_KEY", "FALLBACK"]


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
    requirement_id: str
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
