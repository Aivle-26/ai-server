from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.api_types import (
    LLMStatus,
    MemberId,
    ProjectId,
    RequirementId,
    WbsId,
)


RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
ActionStatus = Literal["TODO", "IN_PROGRESS", "DONE", "BLOCKED"]
ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED", "REVISED"]


class SourceReference(BaseModel):
    document_id: str | None = Field(default=None, min_length=1, max_length=200)
    document_name: str | None = Field(default=None, min_length=1, max_length=500)
    page: int | None = Field(default=None, ge=1)
    excerpt: str | None = Field(default=None, max_length=5_000)


class MeetingDocument(BaseModel):
    document_id: str = Field(min_length=1, max_length=200)
    file_name: str = Field(min_length=1, max_length=255)
    meeting_title: str | None = Field(default=None, min_length=1, max_length=300)
    meeting_date: date | None = None
    attendees: list[str] = Field(default_factory=list, max_length=500)
    text: str = Field(min_length=1, max_length=200_000)


class DecisionLog(BaseModel):
    decision_title: str = Field(min_length=1, max_length=500)
    decision_detail: str = Field(min_length=1, max_length=10_000)
    related_requirement_id: RequirementId | None = None
    related_wbs_id: WbsId | None = None
    owner: str | None = Field(default=None, min_length=1, max_length=200)
    source: SourceReference | None = None


class ActionItem(BaseModel):
    action_item: str = Field(min_length=1, max_length=2_000)
    owner: str | None = Field(default=None, min_length=1, max_length=200)
    due_date: date | None = None
    status: ActionStatus = "TODO"
    related_requirement_id: RequirementId | None = None
    related_wbs_id: WbsId | None = None
    source: SourceReference | None = None


class IssueRiskChangeCandidate(BaseModel):
    risk_title: str = Field(min_length=1, max_length=500)
    risk_type: str = Field(min_length=1, max_length=200)
    change_type: Literal["NEW", "UPDATE", "CLOSE"] = "NEW"
    risk_level: RiskLevel = "LOW"
    reason: str = Field(min_length=1, max_length=5_000)
    related_issue_id: str | None = Field(default=None, min_length=1, max_length=200)
    related_requirement_id: RequirementId | None = None
    related_wbs_id: WbsId | None = None
    source: SourceReference | None = None


class MeetingAnalysisRequest(BaseModel):
    project_id: ProjectId
    project_name: str | None = Field(default=None, min_length=1, max_length=200)
    meeting_document: MeetingDocument
    enable_llm: bool = True


class MeetingAnalysisResponse(BaseModel):
    project_id: ProjectId
    meeting_summary: str
    decision_logs: list[DecisionLog]
    action_items: list[ActionItem]
    issue_risk_changes: list[IssueRiskChangeCandidate]
    missing_owner_count: int = Field(ge=0)
    missing_due_date_count: int = Field(ge=0)
    risk_missing_owner_count: int = Field(default=0, ge=0)
    risk_missing_link_count: int = Field(default=0, ge=0)
    generated_at: datetime
    llm_status: LLMStatus


class WbsTaskSnapshot(BaseModel):
    wbs_id: WbsId
    project_id: ProjectId | None = None
    requirement_id: RequirementId | None = None
    parent_wbs_id: WbsId | None = None
    task_name: str = Field(min_length=1, max_length=500)
    task_description: str | None = Field(default=None, max_length=5_000)
    task_type: str | None = Field(default=None, min_length=1, max_length=100)
    assignee_id: MemberId | None = None
    start_date: date | None = None
    due_date: date | None = None
    status: ActionStatus
    progress_rate: float = Field(ge=0, le=100)
    estimated_man_day: float | None = Field(default=None, ge=0)
    actual_man_day: float | None = Field(default=None, ge=0)
    deliverable_id: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_task_dates(self) -> "WbsTaskSnapshot":
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValueError("due_date must not be before start_date")
        return self


class WeeklyReportRequest(BaseModel):
    project_id: ProjectId
    project_name: str | None = Field(default=None, min_length=1, max_length=200)
    week_start: date
    week_end: date
    wbs_tasks: list[WbsTaskSnapshot] = Field(max_length=1_000)
    completed_action_items: list[ActionItem] = Field(default_factory=list, max_length=1_000)
    open_risks: list[IssueRiskChangeCandidate] = Field(default_factory=list, max_length=1_000)
    enable_llm: bool = True

    @model_validator(mode="after")
    def validate_week(self) -> "WeeklyReportRequest":
        if self.week_end < self.week_start:
            raise ValueError("week_end must not be before week_start")
        return self


class WeeklyReportResponse(BaseModel):
    project_id: ProjectId
    week_start: date
    week_end: date
    progress_summary: str
    completed_work: list[str]
    delayed_work: list[str]
    risk_summary: list[str]
    next_week_plan: list[str]
    report_draft: str
    generated_at: datetime
    llm_status: LLMStatus


class ApprovedReport(BaseModel):
    report_id: str = Field(min_length=1, max_length=200)
    report_title: str = Field(min_length=1, max_length=500)
    report_type: Literal["WEEKLY", "MONTHLY", "FINAL"]
    approved_at: datetime | None = None
    content: str = Field(min_length=1, max_length=200_000)


class ExecutionResult(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    item_name: str = Field(min_length=1, max_length=500)
    planned_result: str | None = Field(default=None, max_length=10_000)
    actual_result: str | None = Field(default=None, max_length=10_000)
    status: Literal["DONE", "PARTIAL", "NOT_DONE"]
    evidence: str | None = Field(default=None, max_length=10_000)


class FinalReportRequest(BaseModel):
    project_id: ProjectId
    project_name: str | None = Field(default=None, min_length=1, max_length=200)
    approved_reports: list[ApprovedReport] = Field(max_length=500)
    execution_results: list[ExecutionResult] = Field(max_length=2_000)
    remaining_risks: list[IssueRiskChangeCandidate] = Field(default_factory=list, max_length=1_000)
    enable_llm: bool = True


class FinalReportResponse(BaseModel):
    project_id: ProjectId
    final_summary: str
    achievement_summary: list[str]
    incomplete_items: list[str]
    remaining_risk_summary: list[str]
    final_report_draft: str
    generated_at: datetime
    llm_status: LLMStatus


class DeliverableDocument(BaseModel):
    deliverable_id: str = Field(min_length=1, max_length=200)
    document_id: str = Field(min_length=1, max_length=200)
    document_name: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=100_000)
    page: int | None = Field(default=None, ge=1)
    requirement_id: RequirementId | None = None
    wbs_id: WbsId | None = None
    review_status: ApprovalStatus | None = None


class DeliverableRagRequest(BaseModel):
    project_id: ProjectId
    question: str = Field(min_length=1, max_length=2_000)
    deliverable_documents: list[DeliverableDocument] = Field(min_length=1, max_length=100)
    enable_llm: bool = True


class RagSource(BaseModel):
    deliverable_id: str
    document_id: str
    document_name: str
    page: int | None = Field(default=None, ge=1)
    excerpt: str
    requirement_id: RequirementId | None = None
    wbs_id: WbsId | None = None
    review_status: ApprovalStatus | None = None


class DeliverableRagResponse(BaseModel):
    project_id: ProjectId
    answer: str
    sources: list[RagSource]
    generated_at: datetime
    llm_status: LLMStatus
