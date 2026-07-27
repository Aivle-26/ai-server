from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


# =========================================================
# 1. 영향도 평가
# =========================================================

class ImpactAssessmentRequest(BaseModel):
    project_id: int
    requirement_id: int | None = None
    change_title: str
    change_description: str

    affected_task_count: int = Field(default=0, ge=0)
    affected_member_count: int = Field(default=0, ge=0)
    remaining_days: int = Field(default=0, ge=0)
    additional_work_days: int = Field(default=0, ge=0)

    scope_changed: bool = False
    database_changed: bool = False
    api_changed: bool = False
    ui_changed: bool = False


class ImpactAssessmentResponse(BaseModel):
    project_id: int
    requirement_id: int | None
    impact_score: int
    impact_level: RiskLevel

    schedule_impact_score: int
    scope_impact_score: int
    resource_impact_score: int
    technical_impact_score: int

    risk_factors: list[str]
    recommended_actions: list[str]


# =========================================================
# 2. 담당자 재배정
# =========================================================

class CurrentAssignee(BaseModel):
    member_id: int
    member_name: str
    skills: list[str] = []
    workload_rate: float = Field(default=0, ge=0, le=100)
    overdue_task_count: int = Field(default=0, ge=0)


class CandidateMember(BaseModel):
    member_id: int
    member_name: str
    role: str
    skills: list[str] = []
    workload_rate: float = Field(default=0, ge=0, le=100)
    overdue_task_count: int = Field(default=0, ge=0)


class AssigneeReassignmentRequest(BaseModel):
    project_id: int
    task_id: int
    task_name: str
    required_role: str
    required_skills: list[str] = []
    current_assignee: CurrentAssignee
    candidates: list[CandidateMember]


class AssigneeCandidateResult(BaseModel):
    member_id: int
    member_name: str
    match_score: int
    skill_match_rate: float
    workload_rate: float
    overdue_task_count: int
    reason: str


class AssigneeReassignmentResponse(BaseModel):
    project_id: int
    task_id: int
    reassignment_required: bool
    current_assignee_risk_score: int
    current_assignee_risk_level: RiskLevel
    recommended_assignee: AssigneeCandidateResult | None
    alternative_candidates: list[AssigneeCandidateResult]
    reasons: list[str]


# =========================================================
# 3. 산출물 보안 검사
# =========================================================

class ArtifactSecurityRequest(BaseModel):
    project_id: int
    artifact_name: str
    artifact_type: str
    text_content: str


class SecurityDetection(BaseModel):
    detection_type: str
    count: int
    description: str


class ArtifactSecurityResponse(BaseModel):
    project_id: int
    artifact_name: str
    security_risk_score: int
    security_risk_level: RiskLevel
    registration_allowed: bool
    detections: list[SecurityDetection]
    masked_content: str
    recommendations: list[str]


# =========================================================
# 4. 산출물 등록 및 상태 점검
# =========================================================

class RegisteredArtifact(BaseModel):
    artifact_name: str
    artifact_type: str
    version: str | None = None
    status: str = "DRAFT"
    approved: bool = False
    submitted_date: date | None = None
    due_date: date | None = None


class ArtifactStatusRequest(BaseModel):
    project_id: int
    required_artifacts: list[str]
    registered_artifacts: list[RegisteredArtifact]


class ArtifactStatusResponse(BaseModel):
    project_id: int
    required_count: int
    registered_count: int
    approved_count: int
    completion_rate: float
    approval_rate: float
    missing_artifacts: list[str]
    unapproved_artifacts: list[str]
    overdue_artifacts: list[str]
    risk_score: int
    risk_level: RiskLevel
    recommendations: list[str]


# =========================================================
# 5. 팀원별 업무 지연 분석
# =========================================================

class MemberTaskStatus(BaseModel):
    member_id: int
    member_name: str
    assigned_task_count: int = Field(ge=0)
    completed_task_count: int = Field(ge=0)
    overdue_task_count: int = Field(ge=0)
    in_progress_task_count: int = Field(default=0, ge=0)
    average_delay_days: float = Field(default=0, ge=0)
    days_since_last_update: int = Field(default=0, ge=0)


class MemberDelayRequest(BaseModel):
    project_id: int
    members: list[MemberTaskStatus]


class MemberDelayResult(BaseModel):
    member_id: int
    member_name: str
    completion_rate: float
    overdue_rate: float
    delay_score: int
    risk_level: RiskLevel
    reasons: list[str]
    recommended_action: str


class MemberDelayResponse(BaseModel):
    project_id: int
    analyzed_member_count: int
    high_risk_member_count: int
    member_results: list[MemberDelayResult]


# =========================================================
# 6. 일정 및 WBS 신호등 리스크 분석
# =========================================================

TrafficLight = Literal["GREEN", "YELLOW", "RED"]
ScheduleRiskLevel = Literal["양호", "보통", "위험"]


class ScheduleWBSItem(BaseModel):
    task_id: int
    task_name: str
    start_date: date
    due_date: date

    progress: float = Field(
        default=0,
        ge=0,
        le=100,
        description="현재 업무 진행률",
    )

    status: str = Field(
        default="TODO",
        description="TODO, IN_PROGRESS, DONE 등의 업무 상태",
    )

    @model_validator(mode="after")
    def validate_schedule_dates(self):
        if self.due_date < self.start_date:
            raise ValueError(
                "due_date는 start_date보다 빠를 수 없습니다."
            )

        return self


class ScheduleWBSRiskRequest(BaseModel):
    project_id: int

    evaluation_date: date = Field(
        description="리스크를 평가하는 기준 날짜",
    )

    tasks: list[ScheduleWBSItem]


class ScheduleWBSRiskItemResult(BaseModel):
    task_id: int
    task_name: str

    progress: float
    expected_progress: float
    progress_gap: float

    overdue_days: int
    days_until_due: int

    risk_score: int

    traffic_light: TrafficLight
    risk_level: ScheduleRiskLevel

    reasons: list[str]
    recommended_action: str


class ScheduleWBSRiskResponse(BaseModel):
    project_id: int
    evaluation_date: date

    total_task_count: int

    green_count: int
    yellow_count: int
    red_count: int

    overall_traffic_light: TrafficLight
    overall_risk_level: ScheduleRiskLevel
    overall_risk_score: int

    task_results: list[ScheduleWBSRiskItemResult]