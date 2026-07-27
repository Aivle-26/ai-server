import re
from datetime import date

from fastapi import APIRouter, HTTPException

from app.schemas.risk_api import (
    ArtifactSecurityRequest,
    ArtifactSecurityResponse,
    ArtifactStatusRequest,
    ArtifactStatusResponse,
    AssigneeCandidateResult,
    AssigneeReassignmentRequest,
    AssigneeReassignmentResponse,
    ImpactAssessmentRequest,
    ImpactAssessmentResponse,
    MemberDelayRequest,
    MemberDelayResponse,
    MemberDelayResult,

    # 일정/WBS 리스크
    ScheduleWBSRiskRequest,
    ScheduleWBSRiskResponse,
    ScheduleWBSRiskItemResult,

    SecurityDetection,
)

router = APIRouter(
    prefix="/api/v1/risk",
    tags=["Risk"],
)


def get_risk_level(score: int) -> str:
    if score >= 85:
        return "CRITICAL"
    if score >= 65:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


# =========================================================
# 1. 영향도 평가 API
# =========================================================

@router.post(
    "/impact-assessment",
    response_model=ImpactAssessmentResponse,
    summary="요구사항 변경 영향도 평가",
)
def assess_change_impact(
    request: ImpactAssessmentRequest,
) -> ImpactAssessmentResponse:

    schedule_score = 0

    if request.additional_work_days > 0:
        schedule_score += min(request.additional_work_days * 8, 60)

    if request.remaining_days == 0 and request.additional_work_days > 0:
        schedule_score += 40
    elif (
        request.remaining_days > 0
        and request.additional_work_days >= request.remaining_days
    ):
        schedule_score += 30
    elif (
        request.remaining_days > 0
        and request.additional_work_days
        >= request.remaining_days * 0.5
    ):
        schedule_score += 20

    schedule_score = min(schedule_score, 100)

    scope_score = min(
        request.affected_task_count * 10
        + (30 if request.scope_changed else 0),
        100,
    )

    resource_score = min(
        request.affected_member_count * 15,
        100,
    )

    technical_change_count = sum(
        [
            request.database_changed,
            request.api_changed,
            request.ui_changed,
        ]
    )

    technical_score = min(
        technical_change_count * 25,
        100,
    )

    impact_score = round(
        schedule_score * 0.35
        + scope_score * 0.30
        + resource_score * 0.20
        + technical_score * 0.15
    )

    risk_factors: list[str] = []
    recommended_actions: list[str] = []

    if schedule_score >= 50:
        risk_factors.append(
            "남은 일정 대비 추가 작업량이 많습니다."
        )
        recommended_actions.append(
            "프로젝트 일정과 마일스톤을 다시 산정하세요."
        )

    if request.scope_changed:
        risk_factors.append(
            "기존 요구사항의 범위가 변경되었습니다."
        )
        recommended_actions.append(
            "변경 범위에 대한 PM 승인을 진행하세요."
        )

    if request.affected_task_count >= 3:
        risk_factors.append(
            f"관련 업무 {request.affected_task_count}개가 영향을 받습니다."
        )
        recommended_actions.append(
            "관련 WBS와 업무 우선순위를 수정하세요."
        )

    if request.affected_member_count >= 2:
        risk_factors.append(
            f"팀원 {request.affected_member_count}명이 영향을 받습니다."
        )
        recommended_actions.append(
            "담당자 업무량과 재배정 필요 여부를 검토하세요."
        )

    if technical_change_count > 0:
        changed_areas = []

        if request.database_changed:
            changed_areas.append("데이터베이스")
        if request.api_changed:
            changed_areas.append("API")
        if request.ui_changed:
            changed_areas.append("UI")

        risk_factors.append(
            f"{', '.join(changed_areas)} 변경이 필요합니다."
        )
        recommended_actions.append(
            "변경 대상에 대한 설계 및 회귀 테스트를 진행하세요."
        )

    if not risk_factors:
        risk_factors.append(
            "현재 확인된 주요 변경 위험이 없습니다."
        )
        recommended_actions.append(
            "기존 계획대로 변경 작업을 진행하세요."
        )

    return ImpactAssessmentResponse(
        project_id=request.project_id,
        requirement_id=request.requirement_id,
        impact_score=impact_score,
        impact_level=get_risk_level(impact_score),
        schedule_impact_score=schedule_score,
        scope_impact_score=scope_score,
        resource_impact_score=resource_score,
        technical_impact_score=technical_score,
        risk_factors=risk_factors,
        recommended_actions=recommended_actions,
    )


# =========================================================
# 2. 담당자 재배정 API
# =========================================================

@router.post(
    "/assignee-reassignment",
    response_model=AssigneeReassignmentResponse,
    summary="담당자 재배정 위험 분석 및 후보 추천",
)
def recommend_assignee_reassignment(
    request: AssigneeReassignmentRequest,
) -> AssigneeReassignmentResponse:

    current = request.current_assignee

    current_skill_set = {
        skill.strip().lower()
        for skill in current.skills
    }

    required_skill_set = {
        skill.strip().lower()
        for skill in request.required_skills
    }

    if required_skill_set:
        current_match_count = len(
            current_skill_set & required_skill_set
        )
        current_skill_match_rate = (
            current_match_count
            / len(required_skill_set)
            * 100
        )
    else:
        current_skill_match_rate = 100

    current_risk_score = round(
        current.workload_rate * 0.5
        + min(current.overdue_task_count * 15, 30)
        + (100 - current_skill_match_rate) * 0.2
    )
    current_risk_score = min(current_risk_score, 100)

    reasons: list[str] = []

    if current.workload_rate >= 80:
        reasons.append(
            f"현재 담당자 업무량이 {current.workload_rate}%입니다."
        )

    if current.overdue_task_count > 0:
        reasons.append(
            f"현재 담당자의 지연 업무가 "
            f"{current.overdue_task_count}건입니다."
        )

    if current_skill_match_rate < 60:
        reasons.append(
            "현재 담당자의 요구 기술 일치도가 낮습니다."
        )

    reassignment_required = current_risk_score >= 65

    candidate_results: list[AssigneeCandidateResult] = []

    for candidate in request.candidates:
        candidate_skill_set = {
            skill.strip().lower()
            for skill in candidate.skills
        }

        if required_skill_set:
            matched_count = len(
                candidate_skill_set & required_skill_set
            )
            skill_match_rate = (
                matched_count
                / len(required_skill_set)
                * 100
            )
        else:
            skill_match_rate = 100

        role_score = (
            100
            if candidate.role.strip().lower()
            == request.required_role.strip().lower()
            else 30
        )

        workload_score = max(
            0,
            100 - candidate.workload_rate,
        )

        delay_score = max(
            0,
            100 - candidate.overdue_task_count * 25,
        )

        match_score = round(
            skill_match_rate * 0.45
            + role_score * 0.25
            + workload_score * 0.20
            + delay_score * 0.10
        )

        reason = (
            f"기술 일치도 {skill_match_rate:.1f}%, "
            f"업무량 {candidate.workload_rate}%, "
            f"지연 업무 {candidate.overdue_task_count}건"
        )

        candidate_results.append(
            AssigneeCandidateResult(
                member_id=candidate.member_id,
                member_name=candidate.member_name,
                match_score=match_score,
                skill_match_rate=round(
                    skill_match_rate,
                    2,
                ),
                workload_rate=candidate.workload_rate,
                overdue_task_count=(
                    candidate.overdue_task_count
                ),
                reason=reason,
            )
        )

    candidate_results.sort(
        key=lambda item: item.match_score,
        reverse=True,
    )

    recommended = (
        candidate_results[0]
        if candidate_results
        else None
    )

    alternatives = (
        candidate_results[1:4]
        if len(candidate_results) > 1
        else []
    )

    if reassignment_required and recommended:
        reasons.append(
            f"{recommended.member_name} 팀원을 "
            "재배정 후보로 추천합니다."
        )

    if not reasons:
        reasons.append(
            "현재 담당자의 재배정 필요성이 낮습니다."
        )

    return AssigneeReassignmentResponse(
        project_id=request.project_id,
        task_id=request.task_id,
        reassignment_required=reassignment_required,
        current_assignee_risk_score=current_risk_score,
        current_assignee_risk_level=get_risk_level(
            current_risk_score
        ),
        recommended_assignee=recommended,
        alternative_candidates=alternatives,
        reasons=reasons,
    )


# =========================================================
# 3. 산출물 보안 검사 API
# =========================================================

@router.post(
    "/artifact-security",
    response_model=ArtifactSecurityResponse,
    summary="산출물 개인정보 및 보안정보 검사",
)
def inspect_artifact_security(
    request: ArtifactSecurityRequest,
) -> ArtifactSecurityResponse:

    content = request.text_content
    masked_content = content
    detections: list[SecurityDetection] = []
    recommendations: list[str] = []

    patterns = [
        {
            "type": "PHONE_NUMBER",
            "pattern": r"01[016789]-?\d{3,4}-?\d{4}",
            "description": "휴대전화 번호가 포함되어 있습니다.",
            "score": 20,
            "replacement": "[전화번호 마스킹]",
        },
        {
            "type": "EMAIL",
            "pattern": (
                r"[A-Za-z0-9._%+-]+"
                r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
            ),
            "description": "이메일 주소가 포함되어 있습니다.",
            "score": 15,
            "replacement": "[이메일 마스킹]",
        },
        {
            "type": "RESIDENT_NUMBER",
            "pattern": r"\d{6}-?[1-4]\d{6}",
            "description": "주민등록번호 형식이 포함되어 있습니다.",
            "score": 50,
            "replacement": "[주민등록번호 마스킹]",
        },
        {
            "type": "API_KEY",
            "pattern": (
                r"(?i)(api[_-]?key|secret[_-]?key|"
                r"access[_-]?token|password)"
                r"\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{8,}"
            ),
            "description": "API Key 또는 인증정보가 포함되어 있습니다.",
            "score": 50,
            "replacement": "[인증정보 마스킹]",
        },
        {
            "type": "PRIVATE_IP",
            "pattern": (
                r"\b(?:"
                r"10(?:\.\d{1,3}){3}|"
                r"192\.168(?:\.\d{1,3}){2}|"
                r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|"
                r"127(?:\.\d{1,3}){3}|"
                r"localhost"
                r")\b"
            ),
            "description": "사설 IP 주소 또는 localhost가 포함되어 있습니다.",
            "score": 40,
            "replacement": "[사설 IP 마스킹]",
        },

        {
            "type": "PRIVATE_KEY",
            "pattern": (
                r"-----BEGIN "
                r"(RSA |EC |OPENSSH )?PRIVATE KEY-----"
            ),
            "description": "Private Key가 포함되어 있습니다.",
            "score": 70,
            "replacement": "[Private Key 마스킹]",
        },
    ]

    security_score = 0

    for item in patterns:
        matches = re.findall(
            item["pattern"],
            content,
        )

        if not matches:
            continue

        count = len(matches)
        security_score += item["score"] * count

        detections.append(
            SecurityDetection(
                detection_type=item["type"],
                count=count,
                description=item["description"],
            )
        )

        masked_content = re.sub(
            item["pattern"],
            item["replacement"],
            masked_content,
        )

    security_score = min(security_score, 100)

    detection_types = {
        detection.detection_type
        for detection in detections
    }

    if "RESIDENT_NUMBER" in detection_types:
        recommendations.append(
            "주민등록번호를 제거하거나 전체 마스킹하세요."
        )

    if (
        "API_KEY" in detection_types
        or "PRIVATE_KEY" in detection_types
    ):
        recommendations.append(
            "노출된 인증정보를 즉시 폐기하고 새 키를 발급하세요."
        )

    if (
        "PHONE_NUMBER" in detection_types
        or "EMAIL" in detection_types
    ):
        recommendations.append(
            "개인정보를 마스킹한 후 공유 범위를 확인하세요."
        )

    if "PRIVATE_IP" in detection_types:
        recommendations.append(
            "사설 IP 주소를 제거하거나 마스킹한 후 산출물을 공유하세요."
        )


    if not detections:
        recommendations.append(
            "탐지된 개인정보 및 인증정보가 없습니다."
        )

    registration_allowed = security_score < 65

    return ArtifactSecurityResponse(
        project_id=request.project_id,
        artifact_name=request.artifact_name,
        security_risk_score=security_score,
        security_risk_level=get_risk_level(
            security_score
        ),
        registration_allowed=registration_allowed,
        detections=detections,
        masked_content=masked_content,
        recommendations=recommendations,
    )


# =========================================================
# 4. 산출물 등록 및 상태 점검 API
# =========================================================

@router.post(
    "/artifact-status",
    response_model=ArtifactStatusResponse,
    summary="필수 산출물 등록 및 승인 상태 점검",
)
def inspect_artifact_status(
    request: ArtifactStatusRequest,
) -> ArtifactStatusResponse:

    today = date.today()

    registered_names = {
        artifact.artifact_name
        for artifact in request.registered_artifacts
    }

    missing_artifacts = [
        artifact
        for artifact in request.required_artifacts
        if artifact not in registered_names
    ]

    unapproved_artifacts = [
        artifact.artifact_name
        for artifact in request.registered_artifacts
        if not artifact.approved
    ]

    overdue_artifacts = [
        artifact.artifact_name
        for artifact in request.registered_artifacts
        if (
            artifact.due_date is not None
            and artifact.due_date < today
            and not artifact.approved
        )
    ]

    required_count = len(
        request.required_artifacts
    )
    registered_count = sum(
        1
        for name in request.required_artifacts
        if name in registered_names
    )

    approved_count = sum(
        1
        for artifact in request.registered_artifacts
        if (
            artifact.artifact_name
            in request.required_artifacts
            and artifact.approved
        )
    )

    completion_rate = (
        registered_count / required_count * 100
        if required_count > 0
        else 100
    )

    approval_rate = (
        approved_count / required_count * 100
        if required_count > 0
        else 100
    )

    risk_score = round(
        (100 - completion_rate) * 0.5
        + (100 - approval_rate) * 0.3
        + min(len(overdue_artifacts) * 15, 20)
    )
    risk_score = min(risk_score, 100)

    recommendations: list[str] = []

    if missing_artifacts:
        recommendations.append(
            "누락된 산출물을 등록하세요: "
            + ", ".join(missing_artifacts)
        )

    if unapproved_artifacts:
        recommendations.append(
            "미승인 산출물의 검토 및 승인을 진행하세요: "
            + ", ".join(unapproved_artifacts)
        )

    if overdue_artifacts:
        recommendations.append(
            "제출기한이 지난 산출물을 우선 처리하세요: "
            + ", ".join(overdue_artifacts)
        )

    if not recommendations:
        recommendations.append(
            "필수 산출물 등록 및 승인 상태가 정상입니다."
        )

    return ArtifactStatusResponse(
        project_id=request.project_id,
        required_count=required_count,
        registered_count=registered_count,
        approved_count=approved_count,
        completion_rate=round(completion_rate, 2),
        approval_rate=round(approval_rate, 2),
        missing_artifacts=missing_artifacts,
        unapproved_artifacts=unapproved_artifacts,
        overdue_artifacts=overdue_artifacts,
        risk_score=risk_score,
        risk_level=get_risk_level(risk_score),
        recommendations=recommendations,
    )


# =========================================================
# 5. 팀원별 업무 지연 분석 API
# =========================================================

@router.post(
    "/member-delay",
    response_model=MemberDelayResponse,
    summary="팀원별 업무 진행 및 지연 위험 분석",
)
def analyze_member_delay(
    request: MemberDelayRequest,
) -> MemberDelayResponse:

    member_results: list[MemberDelayResult] = []

    for member in request.members:
        if (
            member.completed_task_count
            > member.assigned_task_count
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{member.member_name}의 완료 업무 수가 "
                    "배정 업무 수보다 많습니다."
                ),
            )

        completion_rate = (
            member.completed_task_count
            / member.assigned_task_count
            * 100
            if member.assigned_task_count > 0
            else 100
        )

        overdue_rate = (
            member.overdue_task_count
            / member.assigned_task_count
            * 100
            if member.assigned_task_count > 0
            else 0
        )

        delay_score = round(
            overdue_rate * 0.5
            + min(member.average_delay_days * 6, 25)
            + min(
                member.days_since_last_update * 2,
                20,
            )
            + max(
                0,
                (50 - completion_rate) * 0.1,
            )
        )
        delay_score = min(delay_score, 100)

        reasons: list[str] = []

        if overdue_rate >= 30:
            reasons.append(
                f"전체 업무의 {overdue_rate:.1f}%가 지연되었습니다."
            )

        if member.average_delay_days >= 3:
            reasons.append(
                f"평균 지연 기간이 "
                f"{member.average_delay_days}일입니다."
            )

        if member.days_since_last_update >= 5:
            reasons.append(
                f"마지막 업무 갱신 후 "
                f"{member.days_since_last_update}일이 지났습니다."
            )

        if completion_rate < 50:
            reasons.append(
                f"업무 완료율이 {completion_rate:.1f}%입니다."
            )

        risk_level = get_risk_level(delay_score)

        if risk_level in {"CRITICAL", "HIGH"}:
            recommended_action = (
                "지연 업무의 우선순위를 조정하고 "
                "담당자 재배정 또는 일정 변경을 검토하세요."
            )
        elif risk_level == "MEDIUM":
            recommended_action = (
                "업무 진행 상황을 확인하고 "
                "단기 마감 일정을 재점검하세요."
            )
        else:
            recommended_action = (
                "현재 업무 진행 상태를 유지하세요."
            )

        if not reasons:
            reasons.append(
                "현재 확인된 주요 지연 위험이 없습니다."
            )

        member_results.append(
            MemberDelayResult(
                member_id=member.member_id,
                member_name=member.member_name,
                completion_rate=round(
                    completion_rate,
                    2,
                ),
                overdue_rate=round(
                    overdue_rate,
                    2,
                ),
                delay_score=delay_score,
                risk_level=risk_level,
                reasons=reasons,
                recommended_action=recommended_action,
            )
        )

    high_risk_count = sum(
        1
        for result in member_results
        if result.risk_level in {"HIGH", "CRITICAL"}
    )

    member_results.sort(
        key=lambda result: result.delay_score,
        reverse=True,
    )

    return MemberDelayResponse(
        project_id=request.project_id,
        analyzed_member_count=len(member_results),
        high_risk_member_count=high_risk_count,
        member_results=member_results,
    )

# =========================================================
# 6. 일정 및 WBS 신호등 리스크 분석 API
# =========================================================

@router.post(
    "/schedule-wbs-risk",
    response_model=ScheduleWBSRiskResponse,
    summary="일정 및 WBS 기준 신호등 리스크 분석",
)
def analyze_schedule_wbs_risk(
    request: ScheduleWBSRiskRequest,
) -> ScheduleWBSRiskResponse:

    task_results: list[ScheduleWBSRiskItemResult] = []

    green_count = 0
    yellow_count = 0
    red_count = 0

    for task in request.tasks:
        status = task.status.strip().upper()

        completed_statuses = {
            "DONE",
            "COMPLETED",
            "CLOSED",
            "FINISHED",
        }

        is_completed = (
            status in completed_statuses
            or task.progress >= 100
        )

        total_days = (
            task.due_date - task.start_date
        ).days

        if request.evaluation_date < task.start_date:
            expected_progress = 0.0

        elif request.evaluation_date >= task.due_date:
            expected_progress = 100.0

        elif total_days == 0:
            expected_progress = 100.0

        else:
            elapsed_days = (
                request.evaluation_date
                - task.start_date
            ).days

            expected_progress = (
                elapsed_days / total_days * 100
            )

        expected_progress = round(
            max(
                0.0,
                min(expected_progress, 100.0),
            ),
            2,
        )

        progress_gap = round(
            max(
                0.0,
                expected_progress - task.progress,
            ),
            2,
        )

        overdue_days = max(
            (
                request.evaluation_date
                - task.due_date
            ).days,
            0,
        )

        days_until_due = max(
            (
                task.due_date
                - request.evaluation_date
            ).days,
            0,
        )

        risk_score = 0
        reasons: list[str] = []

        # 1. 마감일 초과
        if overdue_days > 0 and not is_completed:
            if overdue_days >= 7:
                risk_score += 70
            elif overdue_days >= 3:
                risk_score += 60
            else:
                risk_score += 50

            reasons.append(
                f"마감일을 {overdue_days}일 초과했습니다."
            )

        # 2. 예상 진행률과 실제 진행률 차이
        if progress_gap >= 40:
            risk_score += 40
            reasons.append(
                f"예상 진행률보다 "
                f"{progress_gap}%p 부족합니다."
            )

        elif progress_gap >= 20:
            risk_score += 30
            reasons.append(
                f"예상 진행률보다 "
                f"{progress_gap}%p 낮습니다."
            )

        elif progress_gap >= 10:
            risk_score += 15
            reasons.append(
                f"예상 진행률보다 "
                f"{progress_gap}%p 다소 낮습니다."
            )

        # 3. 마감 임박
        if (
            not is_completed
            and 0 <= days_until_due <= 2
            and request.evaluation_date
            <= task.due_date
        ):
            if task.progress < 50:
                risk_score += 35

                reasons.append(
                    "마감일까지 2일 이하이지만 "
                    "진행률이 50% 미만입니다."
                )

            elif task.progress < 80:
                risk_score += 20

                reasons.append(
                    "마감일까지 2일 이하이지만 "
                    "진행률이 80% 미만입니다."
                )

        # 4. 업무 미시작
        if (
            not is_completed
            and status == "TODO"
            and task.progress == 0
            and request.evaluation_date
            > task.start_date
        ):
            risk_score += 25

            reasons.append(
                "시작 예정일이 지났지만 "
                "업무가 시작되지 않았습니다."
            )

        # 완료된 업무는 위험 점수를 0으로 처리
        if is_completed:
            risk_score = 0
            reasons = [
                "업무가 완료되어 일정 위험이 없습니다."
            ]

        risk_score = min(risk_score, 100)

        # 신호등 등급
        if risk_score >= 60:
            traffic_light = "RED"
            risk_level = "위험"

            recommended_action = (
                "지연 원인을 즉시 확인하고 "
                "일정 조정, 담당자 지원 또는 "
                "업무 재배정을 검토하세요."
            )

            red_count += 1

        elif risk_score >= 25:
            traffic_light = "YELLOW"
            risk_level = "보통"

            recommended_action = (
                "업무 진행률과 남은 일정을 점검하고 "
                "지연 가능성을 지속적으로 모니터링하세요."
            )

            yellow_count += 1

        else:
            traffic_light = "GREEN"
            risk_level = "양호"

            recommended_action = (
                "현재 일정과 진행 상태를 유지하세요."
            )

            green_count += 1

        if not reasons:
            reasons.append(
                "현재 일정과 진행률이 정상 범위입니다."
            )

        task_results.append(
            ScheduleWBSRiskItemResult(
                task_id=task.task_id,
                task_name=task.task_name,
                progress=task.progress,
                expected_progress=expected_progress,
                progress_gap=progress_gap,
                overdue_days=overdue_days,
                days_until_due=days_until_due,
                risk_score=risk_score,
                traffic_light=traffic_light,
                risk_level=risk_level,
                reasons=reasons,
                recommended_action=recommended_action,
            )
        )

    task_results.sort(
        key=lambda result: result.risk_score,
        reverse=True,
    )

    total_task_count = len(task_results)

    overall_risk_score = (
        round(
            sum(
                result.risk_score
                for result in task_results
            )
            / total_task_count
        )
        if total_task_count > 0
        else 0
    )

    # 전체 신호등 판단
    if red_count > 0:
        overall_traffic_light = "RED"
        overall_risk_level = "위험"

    elif yellow_count > 0:
        overall_traffic_light = "YELLOW"
        overall_risk_level = "보통"

    else:
        overall_traffic_light = "GREEN"
        overall_risk_level = "양호"

    return ScheduleWBSRiskResponse(
        project_id=request.project_id,
        evaluation_date=request.evaluation_date,
        total_task_count=total_task_count,
        green_count=green_count,
        yellow_count=yellow_count,
        red_count=red_count,
        overall_traffic_light=overall_traffic_light,
        overall_risk_level=overall_risk_level,
        overall_risk_score=overall_risk_score,
        task_results=task_results,
    )