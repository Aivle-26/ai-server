from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
ActionStatus = Literal["TODO", "IN_PROGRESS", "DONE", "BLOCKED"]
ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED", "REVISED"]


class SourceReference(BaseModel):
    document_id: str | None = None
    document_name: str | None = None
    page: int | None = None
    excerpt: str | None = None


class MeetingDocument(BaseModel):
    document_id: str
    file_name: str
    meeting_title: str | None = None
    meeting_date: date | None = None
    attendees: list[str] = Field(default_factory=list)
    text: str


class DecisionLog(BaseModel):
    decision_title: str
    decision_detail: str
    related_requirement_id: str | None = None
    related_wbs_id: str | None = None
    owner: str | None = None
    source: SourceReference | None = None


class ActionItem(BaseModel):
    action_item: str
    owner: str | None = None
    due_date: date | None = None
    status: ActionStatus = "TODO"
    related_requirement_id: str | None = None
    related_wbs_id: str | None = None
    source: SourceReference | None = None


class IssueRiskChangeCandidate(BaseModel):
    risk_title: str
    risk_type: str
    change_type: Literal["NEW", "UPDATE", "CLOSE"] = "NEW"
    risk_level: RiskLevel = "LOW"
    reason: str
    related_issue_id: str | None = None
    related_requirement_id: str | None = None
    related_wbs_id: str | None = None
    source: SourceReference | None = None


class MeetingAnalysisRequest(BaseModel):
    project_id: int
    project_name: str | None = None
    meeting_document: MeetingDocument
    enable_llm: bool = True


class MeetingAnalysisResponse(BaseModel):
    project_id: int
    meeting_summary: str
    decision_logs: list[DecisionLog]
    action_items: list[ActionItem]
    issue_risk_changes: list[IssueRiskChangeCandidate]
    missing_owner_count: int
    missing_due_date_count: int
    risk_missing_owner_count: int = 0
    risk_missing_link_count: int = 0
    generated_at: datetime
    llm_status: str


class WbsTaskSnapshot(BaseModel):
    wbs_id: str
    project_id: int | None = None
    requirement_id: str | None = None
    parent_wbs_id: str | None = None
    task_name: str
    task_description: str | None = None
    task_type: str | None = None
    assignee_id: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    status: ActionStatus
    progress_rate: float = Field(ge=0, le=100)
    estimated_man_day: float | None = None
    actual_man_day: float | None = None
    deliverable_id: str | None = None


class WeeklyReportRequest(BaseModel):
    project_id: int
    project_name: str | None = None
    week_start: date
    week_end: date
    wbs_tasks: list[WbsTaskSnapshot]
    completed_action_items: list[ActionItem] = Field(default_factory=list)
    open_risks: list[IssueRiskChangeCandidate] = Field(default_factory=list)
    enable_llm: bool = True


class WeeklyReportResponse(BaseModel):
    project_id: int
    week_start: date
    week_end: date
    progress_summary: str
    completed_work: list[str]
    delayed_work: list[str]
    risk_summary: list[str]
    next_week_plan: list[str]
    report_draft: str
    generated_at: datetime
    llm_status: str


class ApprovedReport(BaseModel):
    report_id: str
    report_title: str
    report_type: Literal["WEEKLY", "MONTHLY", "FINAL"]
    approved_at: datetime | None = None
    content: str


class ExecutionResult(BaseModel):
    item_id: str
    item_name: str
    planned_result: str | None = None
    actual_result: str | None = None
    status: Literal["DONE", "PARTIAL", "NOT_DONE"]
    evidence: str | None = None


class FinalReportRequest(BaseModel):
    project_id: int
    project_name: str | None = None
    approved_reports: list[ApprovedReport]
    execution_results: list[ExecutionResult]
    remaining_risks: list[IssueRiskChangeCandidate] = Field(default_factory=list)
    enable_llm: bool = True


class FinalReportResponse(BaseModel):
    project_id: int
    final_summary: str
    achievement_summary: list[str]
    incomplete_items: list[str]
    remaining_risk_summary: list[str]
    final_report_draft: str
    generated_at: datetime
    llm_status: str


class DeliverableDocument(BaseModel):
    deliverable_id: str
    document_id: str
    document_name: str
    text: str
    page: int | None = None
    requirement_id: str | None = None
    wbs_id: str | None = None
    review_status: str | None = None


class DeliverableRagRequest(BaseModel):
    project_id: int
    question: str
    deliverable_documents: list[DeliverableDocument]
    enable_llm: bool = True


class RagSource(BaseModel):
    deliverable_id: str
    document_id: str
    document_name: str
    page: int | None = None
    excerpt: str
    requirement_id: str | None = None
    wbs_id: str | None = None
    review_status: str | None = None


class DeliverableRagResponse(BaseModel):
    project_id: int
    answer: str
    sources: list[RagSource]
    generated_at: datetime
    llm_status: str