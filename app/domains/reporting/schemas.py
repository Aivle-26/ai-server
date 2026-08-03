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

FindingType = Literal[
    "MISSING_FOLLOW_UP",
    "MISSING_RESPONSE_PLAN",
    "POTENTIAL_RISK",
    "DEPENDENCY",
    "CONFLICT",
    "MISSING_OWNER",
    "MISSING_DUE_DATE",
    "NEEDS_CLARIFICATION",
    "MISSING_REQUIRED_WORK",
    "OVERDUE",
]

ReviewStatus = Literal["PENDING", "APPROVED", "MODIFIED", "REJECTED"]
FinalReviewStatus = Literal["APPROVED", "MODIFIED", "REJECTED"]
ConfidenceLevel = Literal["LOW", "MEDIUM", "HIGH"]
ProjectStatus = Literal["ON_TRACK", "AT_RISK", "OFF_TRACK"]
PriorityLevel = Literal["LOW", "MEDIUM", "HIGH"]
DetectionSource = Literal["RULE", "LLM", "RULE_AND_LLM"]
AssignmentStatus = Literal["ASSIGNED", "PM_DECISION_REQUIRED"]
EffectiveActionStatus = Literal["INCLUDED", "EXCLUDED"]
TaskType = Literal[
    "PLANNING",
    "FRONTEND",
    "BACKEND",
    "AI",
    "DATA",
    "QA",
    "DEVOPS",
    "DOCUMENT",
    "OTHER",
]
SourceDataType = Literal[
    "WEEKLY_SCRUM",
    "JIRA_ISSUE",
    "GITHUB_ISSUE",
    "GITHUB_PR",
    "SLACK_MESSAGE",
    "MEETING_ACTION",
    "WBS_TASK",
    "REQUIREMENT",
    "DELIVERABLE",
    "OTHER",
]

ReferenceDocumentType = Literal[
    "PROJECT_GOAL",
    "REQUIREMENT_SPEC",
    "FUNCTION_SPEC",
    "MILESTONE",
    "PREVIOUS_WEEK_PLAN",
    "TEAM_RULE",
    "OTHER",
]


class ScrumItem(BaseModel):
    item_id: str | None = None
    title: str
    description: str | None = None
    task_type: TaskType = "OTHER"
    owner_id: str | None = None
    owner: str | None = None
    due_date: date | None = None
    status: ActionStatus | None = None
    evidence_text: str | None = None
    done_condition: str | None = None
    estimated_hours: float | None = Field(default=None, ge=0)
    carryover_count: int = Field(default=0, ge=0)
    dependency_ids: list[str] = Field(default_factory=list)
    related_task_ids: list[str] = Field(default_factory=list)
    integration_required: bool = False

    source_type: SourceDataType = "WEEKLY_SCRUM"
    source_reference_id: str | None = None
    requirement_id: str | None = None
    wbs_id: str | None = None
    deliverable_id: str | None = None

    source_member_id: str | None = None
    source_member_name: str | None = None
    source_member_role: str | None = None


class WeeklyMemberUpdate(BaseModel):
    member_id: str | None = None
    member_name: str
    role: str | None = None
    weekly_goal: list[str] = Field(default_factory=list)
    completed_tasks: list[ScrumItem] = Field(default_factory=list)
    in_progress_tasks: list[ScrumItem] = Field(default_factory=list)
    delayed_tasks: list[ScrumItem] = Field(default_factory=list)
    issues: list[ScrumItem] = Field(default_factory=list)
    reported_risks: list[ScrumItem] = Field(default_factory=list)
    next_week_tasks: list[ScrumItem] = Field(default_factory=list)
    requests: list[ScrumItem] = Field(default_factory=list)


class TeamMemberCapacity(BaseModel):
    member_id: str
    member_name: str
    role: str | None = None
    department: str | None = None
    skills: list[str] = Field(default_factory=list)
    availability_hours: float = Field(default=40, ge=0)
    current_workload_hours: float = Field(default=0, ge=0)
    leave_start: date | None = None
    leave_end: date | None = None


class ReferenceDocument(BaseModel):
    document_id: str | None = None
    document_type: ReferenceDocumentType = "OTHER"
    title: str
    content: str


class ScrumEvidence(BaseModel):
    source_type: Literal["WEEKLY_SCRUM", "REFERENCE_DOCUMENT", "AI_INFERENCE"]
    member_id: str | None = None
    member_name: str | None = None
    role: str | None = None
    document_id: str | None = None
    document_title: str | None = None
    item_id: str | None = None
    source_reference_id: str | None = None
    requirement_id: str | None = None
    wbs_id: str | None = None
    deliverable_id: str | None = None
    text: str


class AiReviewFinding(BaseModel):
    finding_id: str
    rule_code: str | None = None
    detection_source: DetectionSource = "RULE"
    reference_document_ids: list[str] = Field(default_factory=list)
    type: FindingType
    title: str
    description: str
    evidence: list[ScrumEvidence] = Field(default_factory=list)
    impact: str | None = None
    recommended_action: str | None = None
    confidence: ConfidenceLevel = "MEDIUM"
    target_item_ids: list[str] = Field(default_factory=list)
    suggested_owner_id: str | None = None
    suggested_owner: str | None = None
    suggested_due_date: date | None = None
    review_status: ReviewStatus = "PENDING"
    review_comment: str | None = None
    pm_modified_title: str | None = None
    pm_modified_description: str | None = None
    pm_modified_action: str | None = None


class NextWeekActionPlan(BaseModel):
    action_id: str
    source_item_id: str | None = None
    title: str
    owner_id: str | None = None
    owner: str | None = None
    assignment_status: AssignmentStatus = "PM_DECISION_REQUIRED"
    due_date: date | None = None
    priority: PriorityLevel = "MEDIUM"
    done_condition: str | None = None
    reason: str | None = None
    source_finding_id: str | None = None
    source_finding_ids: list[str] = Field(default_factory=list)
    dependency_action_ids: list[str] = Field(default_factory=list)
    requirement_id: str | None = None
    wbs_id: str | None = None
    deliverable_id: str | None = None
    review_status: ReviewStatus = "PENDING"
    review_comment: str | None = None
    pm_modified_title: str | None = None
    pm_modified_owner_id: str | None = None
    pm_modified_owner: str | None = None
    pm_modified_due_date: date | None = None
    pm_modified_priority: PriorityLevel | None = None
    pm_modified_done_condition: str | None = None
    pm_modified_reason: str | None = None
    effective_status: EffectiveActionStatus | None = None
    exclusion_reason: str | None = None

    @model_validator(mode="after")
    def sync_assignment_status(self):
        effective_owner_id = self.pm_modified_owner_id or self.owner_id
        effective_owner = self.pm_modified_owner or self.owner
        self.assignment_status = (
            "ASSIGNED"
            if effective_owner_id or effective_owner
            else "PM_DECISION_REQUIRED"
        )
        return self


class WeeklyScrumFactSummary(BaseModel):
    team_members: list[TeamMemberCapacity] = Field(default_factory=list)
    weekly_goals: list[str] = Field(default_factory=list)
    completed_tasks: list[ScrumItem] = Field(default_factory=list)
    in_progress_tasks: list[ScrumItem] = Field(default_factory=list)
    delayed_tasks: list[ScrumItem] = Field(default_factory=list)
    issues: list[ScrumItem] = Field(default_factory=list)
    reported_risks: list[ScrumItem] = Field(default_factory=list)
    next_week_tasks: list[ScrumItem] = Field(default_factory=list)
    requests: list[ScrumItem] = Field(default_factory=list)
    missing_update_members: list[str] = Field(default_factory=list)


class TeamMemberSummary(BaseModel):
    member_id: str | None = None
    member_name: str
    role: str | None = None
    summary: str
    key_completed_tasks: list[str] = Field(default_factory=list)
    key_in_progress_tasks: list[str] = Field(default_factory=list)
    key_issues: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    next_week_focus: list[str] = Field(default_factory=list)


class WeeklyTeamSummary(BaseModel):
    overall_status: ProjectStatus
    executive_summary: str
    team_progress: list[str] = Field(default_factory=list)
    member_summaries: list[TeamMemberSummary] = Field(default_factory=list)
    key_issues: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    next_week_plan_summary: list[str] = Field(default_factory=list)


class WeeklyScrumSummarizeRequest(BaseModel):
    project_id: int
    project_name: str | None = None
    week_start: date
    week_end: date
    sprint_goal: str | None = None
    expected_members: list[str] = Field(default_factory=list)
    team_members: list[TeamMemberCapacity] = Field(default_factory=list)
    member_updates: list[WeeklyMemberUpdate]
    enable_llm: bool = True

    @model_validator(mode="after")
    def validate_period_and_updates(self):
        if self.week_start > self.week_end:
            raise ValueError("week_start는 week_end보다 늦을 수 없습니다.")
        if not self.member_updates:
            raise ValueError("member_updates는 최소 1명 이상이어야 합니다.")
        return self


class WeeklyScrumSummarizeResponse(BaseModel):
    project_id: int
    week_start: date
    week_end: date
    fact_summary: WeeklyScrumFactSummary
    team_summary: WeeklyTeamSummary
    completed_task_count: int = 0
    in_progress_task_count: int = 0
    delayed_task_count: int = 0
    issue_count: int = 0
    risk_count: int = 0
    generated_at: datetime
    llm_status: str


class WeeklyScrumReviewRequest(BaseModel):
    project_id: int
    project_name: str | None = None
    week_start: date
    week_end: date
    sprint_goal: str | None = None
    fact_summary: WeeklyScrumFactSummary
    team_summary: WeeklyTeamSummary
    reference_documents: list[ReferenceDocument] = Field(default_factory=list)
    analysis_date: date | None = None
    enable_llm: bool = True


class WeeklyScrumReviewResponse(BaseModel):
    project_id: int
    week_start: date
    week_end: date
    overall_status: ProjectStatus
    review_findings: list[AiReviewFinding]
    finding_count: int = 0
    generated_at: datetime
    llm_status: str


class WeeklyScrumRecommendNextActionsRequest(BaseModel):
    project_id: int
    project_name: str | None = None
    week_start: date
    week_end: date
    fact_summary: WeeklyScrumFactSummary
    team_summary: WeeklyTeamSummary
    review_findings: list[AiReviewFinding] = Field(default_factory=list)
    next_week_start: date | None = None
    next_week_end: date | None = None
    enable_llm: bool = True

    @model_validator(mode="after")
    def validate_next_week_period(self):
        if (self.next_week_start is None) != (self.next_week_end is None):
            raise ValueError("next_week_start와 next_week_end는 함께 입력해야 합니다.")
        if self.next_week_start and self.next_week_end:
            if self.next_week_start > self.next_week_end:
                raise ValueError("next_week_start는 next_week_end보다 늦을 수 없습니다.")
            if self.next_week_start <= self.week_end:
                raise ValueError("다음 주 시작일은 보고 기간 종료일보다 늦어야 합니다.")
        return self


class WeeklyScrumRecommendNextActionsResponse(BaseModel):
    project_id: int
    week_start: date
    week_end: date
    next_week_start: date
    next_week_end: date
    recommended_next_actions: list[NextWeekActionPlan]
    action_count: int = 0
    generated_at: datetime
    llm_status: str


class ReviewedAiReviewFinding(AiReviewFinding):
    review_status: FinalReviewStatus

    @model_validator(mode="after")
    def validate_pm_decision(self):
        if self.review_status == "REJECTED" and not self.review_comment:
            raise ValueError("REJECTED finding에는 review_comment가 필요합니다.")
        if self.review_status == "MODIFIED" and not any((
            self.pm_modified_title,
            self.pm_modified_description,
            self.pm_modified_action,
        )):
            raise ValueError("MODIFIED finding에는 PM 수정값이 하나 이상 필요합니다.")
        return self


class ReviewedNextWeekAction(NextWeekActionPlan):
    review_status: FinalReviewStatus

    @model_validator(mode="after")
    def validate_pm_decision(self):
        if (
            self.review_status == "REJECTED"
            and not self.review_comment
        ):
            raise ValueError(
                "REJECTED action에는 "
                "review_comment가 필요합니다."
            )

        if (
            self.review_status == "MODIFIED"
            and not any(
                (
                    self.pm_modified_title,
                    self.pm_modified_owner_id,
                    self.pm_modified_owner,
                    self.pm_modified_due_date,
                    self.pm_modified_priority,
                    self.pm_modified_done_condition,
                    self.pm_modified_reason,
                )
            )
        ):
            raise ValueError(
                "MODIFIED action에는 "
                "PM 수정값이 하나 이상 필요합니다."
            )

        return self


class WeeklyScrumFinalizeRequest(BaseModel):
    project_id: int
    project_name: str | None = None
    week_start: date
    week_end: date
    fact_summary: WeeklyScrumFactSummary
    team_summary: WeeklyTeamSummary
    reviewed_findings: list[ReviewedAiReviewFinding] = Field(default_factory=list)
    recommended_next_actions: list[ReviewedNextWeekAction] = Field(default_factory=list)
    source_finding_count: int = Field(ge=0)
    source_action_count: int = Field(ge=0)
    enable_llm: bool = True

    @model_validator(mode="after")
    def validate_review_completeness(self):
        if self.source_finding_count != len(self.reviewed_findings):
            raise ValueError("review 단계의 모든 finding에 PM 결정을 입력해야 합니다.")
        if self.source_action_count != len(self.recommended_next_actions):
            raise ValueError("recommend 단계의 모든 action에 PM 결정을 입력해야 합니다.")

        rejected_finding_ids = {
            finding.finding_id
            for finding in self.reviewed_findings
            if finding.review_status == "REJECTED"
        }
        for action in self.recommended_next_actions:
            source_ids = list(action.source_finding_ids)
            if action.source_finding_id and action.source_finding_id not in source_ids:
                source_ids.append(action.source_finding_id)
            automatically_excluded = bool(source_ids) and all(
                finding_id in rejected_finding_ids for finding_id in source_ids
            )
            if action.review_status not in ("APPROVED", "MODIFIED"):
                continue
            if automatically_excluded:
                continue
            effective_owner_id = action.pm_modified_owner_id or action.owner_id
            effective_owner = action.pm_modified_owner or action.owner
            if not effective_owner_id and not effective_owner:
                raise ValueError(
                    f"최종 반영 action({action.action_id})에는 담당자가 필요합니다. "
                    "담당자를 지정해 MODIFIED로 제출하거나 REJECTED로 처리하세요."
                )
        return self


class WeeklyScrumFinalizeResponse(BaseModel):
    project_id: int
    week_start: date
    week_end: date
    included_findings: list[ReviewedAiReviewFinding]
    excluded_findings: list[ReviewedAiReviewFinding]
    included_next_actions: list[ReviewedNextWeekAction]
    excluded_next_actions: list[ReviewedNextWeekAction]
    final_report: str
    generated_at: datetime
    llm_status: str
