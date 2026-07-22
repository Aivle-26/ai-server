from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


LLMStatus = Literal["SUCCEEDED", "SKIPPED_NO_API_KEY", "FALLBACK"]
ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED", "MODIFIED"]
ActionItemStatus = Literal["TODO", "IN_PROGRESS", "DONE", "BLOCKED"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
RiskChangeType = Literal["NEW", "UPDATED", "RESOLVED", "UNCHANGED"]
ReportType = Literal["WEEKLY", "FINAL"]


class SourceReference(BaseModel):
    document_id: str | None = Field(None, description="근거 문서 ID")
    document_name: str | None = Field(None, description="근거 문서명")
    page: int | None = Field(None, description="근거 페이지")
    excerpt: str | None = Field(None, description="근거 문장")


# 1. 회의록 파일 -> 결정 로그, 액션 아이템, 이슈 리스크 변경 후보

class MeetingDocumentInput(BaseModel):
    document_id: str | None = Field(None, description="회의록 문서 ID")
    file_name: str = Field(..., description="회의록 파일명")
    meeting_title: str = Field(..., description="회의 제목")
    meeting_date: date | None = Field(None, description="회의일")
    attendees: list[str] = Field(default_factory=list, description="참석자 목록")
    text: str = Field(..., min_length=10, description="회의록 원문 텍스트")


class DecisionLogCandidate(BaseModel):
    decision_title: str = Field(..., description="결정사항 제목")
    decision_detail: str = Field(..., description="결정사항 상세 내용")
    related_requirement_id: str | None = Field(None, description="연결 요구사항 ID")
    related_wbs_id: str | None = Field(None, description="연결 WBS ID")
    owner: str | None = Field(None, description="결정사항 책임자")
    source: SourceReference | None = Field(None, description="근거 문서 정보")


class ActionItemCandidate(BaseModel):
    action_item: str = Field(..., description="회의에서 도출된 후속 작업")
    owner: str | None = Field(None, description="담당자")
    due_date: date | None = Field(None, description="마감일")
    status: ActionItemStatus = Field("TODO", description="액션 아이템 상태")
    related_requirement_id: str | None = Field(None, description="연결 요구사항 ID")
    related_wbs_id: str | None = Field(None, description="연결 WBS ID")
    source: SourceReference | None = Field(None, description="근거 문서 정보")


class IssueRiskChangeCandidate(BaseModel):
    risk_title: str = Field(..., description="리스크 제목")
    risk_type: str = Field(..., description="리스크 유형")
    change_type: RiskChangeType = Field(..., description="신규/변경/해결/유지 여부")
    risk_level: RiskLevel = Field(..., description="리스크 등급")
    reason: str = Field(..., description="리스크 판단 사유")
    related_issue_id: str | None = Field(None, description="연결 이슈 ID")
    related_requirement_id: str | None = Field(None, description="연결 요구사항 ID")
    related_wbs_id: str | None = Field(None, description="연결 WBS ID")
    source: SourceReference | None = Field(None, description="근거 문서 정보")


class MeetingAnalysisRequest(BaseModel):
    project_id: int = Field(..., gt=0, description="프로젝트 ID")
    project_name: str = Field(..., description="프로젝트명")
    meeting_document: MeetingDocumentInput
    enable_llm: bool = Field(True, description="LLM 사용 여부")


class MeetingAnalysisResponse(BaseModel):
    project_id: int
    meeting_summary: str = Field(..., description="회의 요약")
    decision_logs: list[DecisionLogCandidate] = Field(default_factory=list)
    action_items: list[ActionItemCandidate] = Field(default_factory=list)
    issue_risk_changes: list[IssueRiskChangeCandidate] = Field(default_factory=list)
    missing_owner_count: int = Field(0, description="담당자 누락 액션 아이템 수")
    missing_due_date_count: int = Field(0, description="마감일 누락 액션 아이템 수")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    llm_status: LLMStatus


# 2. WBS 기준 일정 + 완료된 액션 아이템 -> 주간 보고서

class WbsScheduleSnapshot(BaseModel):
    wbs_id: str
    task_name: str
    owner: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    status: ActionItemStatus
    progress_rate: float = Field(..., ge=0, le=100, description="진행률")
    delay_days: int = Field(0, description="지연 일수")


class WeeklyReportRequest(BaseModel):
    project_id: int = Field(..., gt=0)
    project_name: str
    week_start: date
    week_end: date
    wbs_schedules: list[WbsScheduleSnapshot] = Field(default_factory=list)
    completed_action_items: list[ActionItemCandidate] = Field(default_factory=list)
    pending_action_items: list[ActionItemCandidate] = Field(default_factory=list)
    decision_logs: list[DecisionLogCandidate] = Field(default_factory=list)
    issue_risk_changes: list[IssueRiskChangeCandidate] = Field(default_factory=list)
    enable_llm: bool = True


class WeeklyReportResponse(BaseModel):
    project_id: int
    report_type: ReportType = "WEEKLY"
    title: str
    progress_summary: str
    completed_work_summary: str
    pending_work_summary: str
    risk_summary: str
    next_week_plan: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    report_markdown: str = Field(..., description="주간 보고서 본문")
    approval_status: ApprovalStatus = Field("PENDING", description="PM 승인 상태")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    llm_status: LLMStatus


# 3. 승인된 보고서 + 이행 결과 -> 최종 보고서

class ApprovedReportInput(BaseModel):
    report_id: str
    report_type: ReportType
    title: str
    approved_at: datetime | None = None
    report_markdown: str


class ImplementationResultInput(BaseModel):
    item_id: str
    item_type: Literal["ACTION_ITEM", "RISK", "WBS", "DELIVERABLE"]
    title: str
    planned_result: str | None = None
    actual_result: str | None = None
    status: Literal["DONE", "PARTIAL", "NOT_DONE"]
    evidence: SourceReference | None = None


class FinalReportRequest(BaseModel):
    project_id: int = Field(..., gt=0)
    project_name: str
    approved_reports: list[ApprovedReportInput] = Field(default_factory=list)
    implementation_results: list[ImplementationResultInput] = Field(default_factory=list)
    enable_llm: bool = True


class FinalReportResponse(BaseModel):
    project_id: int
    report_type: ReportType = "FINAL"
    title: str
    executive_summary: str
    project_result_summary: str
    unresolved_items: list[str] = Field(default_factory=list)
    lesson_learned: list[str] = Field(default_factory=list)
    final_report_markdown: str
    approval_status: ApprovalStatus = Field("PENDING")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    llm_status: LLMStatus


# 4. 산출물 기반 RAG 챗봇

class RagArtifactInput(BaseModel):
    artifact_id: str
    artifact_name: str
    artifact_type: str
    text: str = Field(..., description="RAG 검색 대상 산출물 텍스트")
    uploaded_at: datetime | None = None


class ArtifactRagQuestionRequest(BaseModel):
    project_id: int = Field(..., gt=0)
    question: str = Field(..., min_length=1)
    artifacts: list[RagArtifactInput] = Field(..., min_length=1)
    enable_llm: bool = True


class ArtifactRagCitation(BaseModel):
    artifact_id: str
    artifact_name: str
    excerpt: str
    relevance_reason: str | None = Field(None, description="해당 근거를 사용한 이유")


class ArtifactRagQuestionResponse(BaseModel):
    project_id: int
    answer: str
    citations: list[ArtifactRagCitation] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    llm_status: LLMStatus