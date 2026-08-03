import re
from datetime import date, datetime, timedelta, timezone

from app.schemas.report import (
    AiReviewFinding,
    NextWeekActionPlan,
    ProjectStatus,
    ReviewedAiReviewFinding,
    ScrumEvidence,
    ScrumItem,
    TeamMemberSummary,
    WeeklyScrumFactSummary,
    WeeklyScrumFinalizeRequest,
    WeeklyScrumFinalizeResponse,
    WeeklyScrumRecommendNextActionsRequest,
    WeeklyScrumRecommendNextActionsResponse,
    WeeklyScrumReviewRequest,
    WeeklyScrumReviewResponse,
    WeeklyScrumSummarizeRequest,
    WeeklyScrumSummarizeResponse,
    WeeklyTeamSummary,
)
from app.services.report_llm_service import ReportLlmService


class ReportService:
    def __init__(self) -> None:
        self.llm_service = ReportLlmService()

    def _tokenize(self, text: str) -> list[str]:
        stopwords = {
            "은",
            "는",
            "이",
            "가",
            "을",
            "를",
            "에",
            "의",
            "와",
            "과",
            "로",
            "으로",
            "누가",
            "언제",
            "까지",
        }
        tokens = re.findall(r"[가-힣A-Za-z0-9_-]{2,}", text)
        return [token for token in tokens if token not in stopwords]

    def _josa(
        self,
        value: str,
        consonant_form: str,
        vowel_form: str,
    ) -> str:
        """
        마지막 한글 글자의 받침 여부에 따라 조사를 선택한다.

        예:
        김남효 + 은/는 -> 김남효는
        플랫폼 + 은/는 -> 플랫폼은
        확정 + 을/를 -> 확정을
        연동 + 이/가 -> 연동이
        """
        normalized = re.sub(
            r"[^가-힣A-Za-z0-9]",
            "",
            value or "",
        )

        if not normalized:
            return vowel_form

        last_character = normalized[-1]

        if "가" <= last_character <= "힣":
            has_final_consonant = (
                ord(last_character) - ord("가")
            ) % 28 != 0

            return (
                consonant_form
                if has_final_consonant
                else vowel_form
            )

        return vowel_form

    def _contains_similar_task(self, title: str, items: list[ScrumItem]) -> bool:
        title_tokens = set(self._tokenize(title))

        for item in items:
            item_tokens = set(self._tokenize(item.title))
            if title == item.title:
                return True
            if title_tokens and len(title_tokens & item_tokens) >= 2:
                return True

        return False

    def _copy_item_with_source(
        self,
        item: ScrumItem,
        member_id: str | None,
        member_name: str,
        role: str | None,
    ) -> ScrumItem:
        return item.model_copy(
            update={
                "source_member_id": member_id,
                "source_member_name": member_name,
                "source_member_role": role,
            }
        )

    def _build_scrum_evidence_from_item(self, item: ScrumItem) -> ScrumEvidence:
        return ScrumEvidence(
            source_type="WEEKLY_SCRUM",
            member_id=item.source_member_id,
            member_name=item.source_member_name,
            role=item.source_member_role,
            item_id=item.item_id,
            source_reference_id=item.source_reference_id or item.item_id,
            requirement_id=item.requirement_id,
            wbs_id=item.wbs_id,
            deliverable_id=item.deliverable_id,
            text=item.evidence_text or item.description or item.title,
        )

    def _build_weekly_scrum_fact_summary(
        self,
        request: WeeklyScrumSummarizeRequest,
    ) -> WeeklyScrumFactSummary:
        submitted_members = {update.member_name for update in request.member_updates}
        missing_update_members = [
            member
            for member in request.expected_members
            if member not in submitted_members
        ]

        fact_summary = WeeklyScrumFactSummary(
            team_members=request.team_members,
            missing_update_members=missing_update_members,
        )

        for update in request.member_updates:
            fact_summary.weekly_goals.extend(update.weekly_goal)

            fact_summary.completed_tasks.extend(
                self._copy_item_with_source(
                    item,
                    update.member_id,
                    update.member_name,
                    update.role,
                )
                for item in update.completed_tasks
            )
            fact_summary.in_progress_tasks.extend(
                self._copy_item_with_source(
                    item,
                    update.member_id,
                    update.member_name,
                    update.role,
                )
                for item in update.in_progress_tasks
            )
            fact_summary.delayed_tasks.extend(
                self._copy_item_with_source(
                    item,
                    update.member_id,
                    update.member_name,
                    update.role,
                )
                for item in update.delayed_tasks
            )
            fact_summary.issues.extend(
                self._copy_item_with_source(
                    item,
                    update.member_id,
                    update.member_name,
                    update.role,
                )
                for item in update.issues
            )
            fact_summary.reported_risks.extend(
                self._copy_item_with_source(
                    item,
                    update.member_id,
                    update.member_name,
                    update.role,
                )
                for item in update.reported_risks
            )
            fact_summary.next_week_tasks.extend(
                self._copy_item_with_source(
                    item,
                    update.member_id,
                    update.member_name,
                    update.role,
                )
                for item in update.next_week_tasks
            )
            fact_summary.requests.extend(
                self._copy_item_with_source(
                    item,
                    update.member_id,
                    update.member_name,
                    update.role,
                )
                for item in update.requests
            )

        return fact_summary

    def _all_task_items(
        self,
        fact_summary: WeeklyScrumFactSummary,
    ) -> list[tuple[str, ScrumItem]]:
        sections = (
            ("COMPLETED", fact_summary.completed_tasks),
            ("IN_PROGRESS", fact_summary.in_progress_tasks),
            ("DELAYED", fact_summary.delayed_tasks),
            ("ISSUE", fact_summary.issues),
            ("RISK", fact_summary.reported_risks),
            ("NEXT_WEEK", fact_summary.next_week_tasks),
            ("REQUEST", fact_summary.requests),
        )
        return [
            (section, item)
            for section, items in sections
            for item in items
        ]

    def _item_identity(self, item: ScrumItem) -> str:
        return (
            item.item_id
            or item.source_reference_id
            or item.wbs_id
            or item.requirement_id
            or "title:" + " ".join(sorted(set(self._tokenize(item.title))))
        )

    def _build_advanced_rule_findings(
        self,
        fact_summary: WeeklyScrumFactSummary,
        analysis_date: date,
    ) -> list[AiReviewFinding]:
        findings: list[AiReviewFinding] = []
        findings.extend(self._build_conflict_findings(fact_summary))
        findings.extend(self._build_dependency_findings(fact_summary))
        findings.extend(self._build_repeated_carryover_findings(fact_summary))
        findings.extend(self._build_integration_test_findings(fact_summary))
        findings.extend(self._build_workload_findings(fact_summary, analysis_date))
        return findings

    def _build_conflict_findings(
        self,
        fact_summary: WeeklyScrumFactSummary,
    ) -> list[AiReviewFinding]:
        grouped: dict[str, list[tuple[str, ScrumItem]]] = {}
        for section, item in self._all_task_items(fact_summary):
            if section in ("ISSUE", "RISK", "REQUEST"):
                continue
            grouped.setdefault(self._item_identity(item), []).append((section, item))

        findings: list[AiReviewFinding] = []
        for identity, occurrences in grouped.items():
            sections = {section for section, _ in occurrences}
            statuses = {item.status for _, item in occurrences if item.status}
            has_completed = "COMPLETED" in sections or "DONE" in statuses
            has_unfinished = bool(
                sections & {"IN_PROGRESS", "DELAYED"}
                or statuses & {"TODO", "IN_PROGRESS", "BLOCKED"}
            )
            if not (has_completed and has_unfinished):
                continue

            items = [item for _, item in occurrences]
            findings.append(AiReviewFinding(
                finding_id="TEMP",
                rule_code="TASK_STATUS_CONFLICT",
                type="CONFLICT",
                title=f"업무 상태 모순 확인 필요: {items[0].title}",
                description="동일하거나 연결된 업무가 완료와 미완료 상태로 동시에 보고되었습니다.",
                evidence=[self._build_scrum_evidence_from_item(item) for item in items],
                impact="완료율과 다음 주 계획이 잘못 계산되고 후속 업무 시작 판단이 왜곡될 수 있습니다.",
                recommended_action="관련 담당자가 실제 상태를 확인하고 하나의 기준 상태로 확정하세요.",
                confidence="HIGH",
                target_item_ids=[identity],
                suggested_owner_id=items[0].owner_id or items[0].source_member_id,
                suggested_owner=items[0].owner or items[0].source_member_name,
            ))
        return findings

    def _build_dependency_findings(
        self,
        fact_summary: WeeklyScrumFactSummary,
    ) -> list[AiReviewFinding]:
        all_items = self._all_task_items(fact_summary)
        item_index: dict[str, tuple[str, ScrumItem]] = {}
        for section, item in all_items:
            for key in (
                item.item_id,
                item.source_reference_id,
                item.wbs_id,
            ):
                if key:
                    item_index[key] = (section, item)

        findings: list[AiReviewFinding] = []
        for section, item in all_items:
            if section not in ("IN_PROGRESS", "DELAYED", "NEXT_WEEK"):
                continue
            for dependency_id in item.dependency_ids:
                dependency = item_index.get(dependency_id)
                if dependency is None:
                    findings.append(AiReviewFinding(
                        finding_id="TEMP",
                        rule_code="UNKNOWN_DEPENDENCY",
                        type="NEEDS_CLARIFICATION",
                        title=f"선행 업무 확인 필요: {item.title}",
                        description=f"선행 업무 ID {dependency_id}가 현재 스크럼 데이터에서 확인되지 않습니다.",
                        evidence=[self._build_scrum_evidence_from_item(item)],
                        impact="선행조건을 확인하지 못하면 일정 순서와 완료 가능성을 판단할 수 없습니다.",
                        recommended_action=f"선행 업무 {dependency_id}의 상태와 담당자를 확인하세요.",
                        confidence="HIGH",
                        target_item_ids=[self._item_identity(item), dependency_id],
                        suggested_owner_id=item.owner_id or item.source_member_id,
                        suggested_owner=item.owner or item.source_member_name,
                    ))
                    continue

                dependency_section, dependency_item = dependency
                dependency_done = (
                    dependency_section == "COMPLETED"
                    or dependency_item.status == "DONE"
                )
                if dependency_done:
                    continue

                findings.append(AiReviewFinding(
                    finding_id="TEMP",
                    rule_code="BLOCKED_BY_UNFINISHED_DEPENDENCY",
                    type="DEPENDENCY",
                    title=f"미완료 선행 업무로 인한 지연 가능성: {item.title}",
                    description=(
                        f"후속 업무 '{item.title}'"
                        f"{self._josa(item.title, '이', '가')} "
                        f"선행 업무 '{dependency_item.title}' "
                        "완료에 의존하지만 아직 완료되지 않았습니다."
                    ),
                    evidence=[
                        self._build_scrum_evidence_from_item(item),
                        self._build_scrum_evidence_from_item(dependency_item),
                    ],
                    impact="후속 업무 착수 또는 완료 일정이 지연될 수 있습니다.",
                    recommended_action=(
                        f"'{dependency_item.title}'"
                        f"{self._josa(dependency_item.title, '을', '를')} "
                        "우선 완료하고 후속 업무 착수 조건을 확인하세요."
                    ),
                    confidence="HIGH",
                    target_item_ids=[self._item_identity(item), dependency_id],
                    suggested_owner_id=(
                        dependency_item.owner_id or dependency_item.source_member_id
                    ),
                    suggested_owner=(
                        dependency_item.owner or dependency_item.source_member_name
                    ),
                ))
        return findings

    def _build_repeated_carryover_findings(
        self,
        fact_summary: WeeklyScrumFactSummary,
    ) -> list[AiReviewFinding]:
        findings: list[AiReviewFinding] = []
        for item in fact_summary.delayed_tasks + fact_summary.in_progress_tasks:
            if item.carryover_count < 2:
                continue
            findings.append(AiReviewFinding(
                finding_id="TEMP",
                rule_code="REPEATED_CARRYOVER",
                type="POTENTIAL_RISK",
                title=f"반복 이월 위험: {item.title}",
                description=f"해당 업무가 {item.carryover_count}주 연속 이월되었습니다.",
                evidence=[self._build_scrum_evidence_from_item(item)],
                impact="원인이 해결되지 않으면 일정 지연이 반복되고 후속 업무가 누적될 수 있습니다.",
                recommended_action="지연 원인을 확인하고 업무 분할, 담당자 보강 또는 범위 조정을 결정하세요.",
                confidence="HIGH",
                target_item_ids=[self._item_identity(item)],
                suggested_owner_id=item.owner_id or item.source_member_id,
                suggested_owner=item.owner or item.source_member_name,
            ))
        return findings

    def _build_integration_test_findings(
        self,
        fact_summary: WeeklyScrumFactSummary,
    ) -> list[AiReviewFinding]:
        integration_sources = [
            item
            for section, item in self._all_task_items(fact_summary)
            if section in ("COMPLETED", "IN_PROGRESS", "DELAYED")
            and item.integration_required
        ]
        if not integration_sources:
            return []

        test_keywords = {"통합", "연동", "integration"}
        test_items = [
            item
            for section, item in self._all_task_items(fact_summary)
            if section in ("COMPLETED", "IN_PROGRESS", "NEXT_WEEK")
            and (
                item.task_type == "QA"
                or bool(test_keywords & set(self._tokenize(item.title.lower())))
            )
            and ("테스트" in item.title or "test" in item.title.lower())
        ]
        if test_items:
            return []

        target_ids = [self._item_identity(item) for item in integration_sources]
        return [AiReviewFinding(
            finding_id="TEMP",
            rule_code="MISSING_INTEGRATION_TEST",
            type="MISSING_REQUIRED_WORK",
            title="프론트·백엔드 통합 테스트 업무 누락",
            description="연동이 필요한 구현 업무가 있지만 통합 또는 연동 테스트 업무가 확인되지 않습니다.",
            evidence=[self._build_scrum_evidence_from_item(item) for item in integration_sources],
            impact="개별 구현이 완료되어도 실제 사용자 흐름에서 API 계약 오류와 재작업이 발생할 수 있습니다.",
            recommended_action="다음 주 계획에 프론트·백엔드 통합 테스트를 추가하세요.",
            confidence="HIGH",
            target_item_ids=target_ids,
            suggested_owner=self._suggest_integration_owner(fact_summary),
        )]

    def _suggest_integration_owner(
        self,
        fact_summary: WeeklyScrumFactSummary,
    ) -> str | None:
        candidates = [
            member
            for member in fact_summary.team_members
            if (member.role or "").upper() in ("QA", "BACKEND", "BE")
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda member: (
                member.current_workload_hours / member.availability_hours
                if member.availability_hours
                else float("inf")
            ),
        ).member_name

    def _build_workload_findings(
        self,
        fact_summary: WeeklyScrumFactSummary,
        analysis_date: date,
    ) -> list[AiReviewFinding]:
        findings: list[AiReviewFinding] = []
        for member in fact_summary.team_members:
            assigned_hours = sum(
                item.estimated_hours or 0
                for item in fact_summary.next_week_tasks
                if item.owner_id == member.member_id or item.owner == member.member_name
            )
            projected = member.current_workload_hours + assigned_hours
            on_leave = bool(
                member.leave_start
                and member.leave_end
                and member.leave_start <= analysis_date <= member.leave_end
            )
            overloaded = (
                member.availability_hours == 0
                or projected > member.availability_hours
            )
            if not (on_leave or overloaded):
                continue

            reason = (
                "분석 기준일에 휴가 기간입니다."
                if on_leave
                else f"예상 업무량 {projected:g}시간이 가용 시간 {member.availability_hours:g}시간을 초과합니다."
            )
            findings.append(AiReviewFinding(
                finding_id="TEMP",
                rule_code="MEMBER_OVERLOAD",
                type="POTENTIAL_RISK",
                title=f"담당자 업무 집중 위험: {member.member_name}",
                description=reason,
                evidence=[ScrumEvidence(
                    source_type="AI_INFERENCE",
                    member_id=member.member_id,
                    member_name=member.member_name,
                    role=member.role,
                    text=reason,
                )],
                impact="업무 지연과 품질 저하, 병목이 발생할 가능성이 있습니다.",
                recommended_action="우선순위를 조정하거나 다른 가용 담당자에게 일부 업무를 재배정하세요.",
                confidence="HIGH",
                suggested_owner_id=member.member_id,
                suggested_owner=member.member_name,
            ))
        return findings

    def _determine_weekly_scrum_status(
        self,
        fact_summary: WeeklyScrumFactSummary,
        findings: list[AiReviewFinding] | None = None,
    ) -> ProjectStatus:
        findings = findings or []
        high_confidence_count = sum(
            1
            for finding in findings
            if finding.confidence == "HIGH"
        )

        if fact_summary.issues or high_confidence_count >= 2:
            return "OFF_TRACK"

        if fact_summary.delayed_tasks or fact_summary.reported_risks or findings:
            return "AT_RISK"

        return "ON_TRACK"

    def _build_fallback_team_summary(
        self,
        request: WeeklyScrumSummarizeRequest,
        fact_summary: WeeklyScrumFactSummary,
    ) -> WeeklyTeamSummary:
        member_summaries: list[TeamMemberSummary] = []

        for update in request.member_updates:
            member_summaries.append(
                TeamMemberSummary(
                    member_id=update.member_id,
                    member_name=update.member_name,
                    role=update.role,
                    summary=(
                        f"{update.member_name}"
                        f"{self._josa(update.member_name, '은', '는')} "
                        f"완료 업무 "
                        f"{len(update.completed_tasks)}건, 진행 중 업무 "
                        f"{len(update.in_progress_tasks)}건, 지연 업무 "
                        f"{len(update.delayed_tasks)}건을 보고했습니다."
                    ),
                    key_completed_tasks=[
                        item.title for item in update.completed_tasks
                    ],
                    key_in_progress_tasks=[
                        item.title for item in update.in_progress_tasks
                    ],
                    key_issues=[
                        item.title for item in update.issues
                    ],
                    key_risks=[
                        item.title for item in update.reported_risks
                    ],
                    next_week_focus=[
                        item.title for item in update.next_week_tasks
                    ],
                )
            )

        overall_status = self._determine_weekly_scrum_status(
            fact_summary,
        )

        # 프로젝트명의 마지막 글자에 맞는 조사(은/는)를 선택한다.
        project_label = request.project_name or "프로젝트"
        project_josa = self._josa(
            project_label,
            "은",
            "는",
        )

        executive_summary = (
            f"이번 주 {project_label}{project_josa} 완료 업무 "
            f"{len(fact_summary.completed_tasks)}건, 진행 중 업무 "
            f"{len(fact_summary.in_progress_tasks)}건, 지연 업무 "
            f"{len(fact_summary.delayed_tasks)}건이 확인되었습니다. "
            f"이슈 {len(fact_summary.issues)}건, 위험 "
            f"{len(fact_summary.reported_risks)}건이 보고되었습니다."
        )

        return WeeklyTeamSummary(
            overall_status=overall_status,
            executive_summary=executive_summary,
            team_progress=[
                item.title for item in fact_summary.completed_tasks
            ],
            member_summaries=member_summaries,
            key_issues=[
                item.title for item in fact_summary.issues
            ],
            key_risks=[
                item.title for item in fact_summary.reported_risks
            ],
            next_week_plan_summary=[
                item.title for item in fact_summary.next_week_tasks
            ],
        )

    def _parse_team_summary(
        self,
        data: dict,
        fallback_summary: WeeklyTeamSummary,
    ) -> WeeklyTeamSummary:
        try:
            payload = fallback_summary.model_dump(mode="json")
            payload.update(
                {
                    "overall_status": data.get(
                        "overall_status",
                        fallback_summary.overall_status,
                    ),
                    "executive_summary": data.get(
                        "executive_summary",
                        fallback_summary.executive_summary,
                    ),
                    "team_progress": data.get(
                        "team_progress",
                        fallback_summary.team_progress,
                    ),
                    "member_summaries": data.get(
                        "member_summaries",
                        [
                            summary.model_dump(mode="json")
                            for summary in fallback_summary.member_summaries
                        ],
                    ),
                    "key_issues": data.get(
                        "key_issues",
                        fallback_summary.key_issues,
                    ),
                    "key_risks": data.get(
                        "key_risks",
                        fallback_summary.key_risks,
                    ),
                    "next_week_plan_summary": data.get(
                        "next_week_plan_summary",
                        fallback_summary.next_week_plan_summary,
                    ),
                }
            )
            return WeeklyTeamSummary(**payload)
        except Exception:
            return fallback_summary

    def summarize_weekly_scrum(
        self,
        request: WeeklyScrumSummarizeRequest,
    ) -> WeeklyScrumSummarizeResponse:
        fact_summary = self._build_weekly_scrum_fact_summary(request)
        fallback_summary = self._build_fallback_team_summary(request, fact_summary)

        team_summary = fallback_summary
        llm_status = "FALLBACK"

        if request.enable_llm:
            llm_result = self.llm_service.summarize_weekly_scrum(
                request=request,
                fact_summary=fact_summary,
                fallback_summary=fallback_summary,
            )

            if llm_result:
                team_summary = self._parse_team_summary(
                    llm_result,
                    fallback_summary,
                )
                llm_status = "SUCCEEDED"

        return WeeklyScrumSummarizeResponse(
            project_id=request.project_id,
            week_start=request.week_start,
            week_end=request.week_end,
            fact_summary=fact_summary,
            team_summary=team_summary,
            completed_task_count=len(fact_summary.completed_tasks),
            in_progress_task_count=len(fact_summary.in_progress_tasks),
            delayed_task_count=len(fact_summary.delayed_tasks),
            issue_count=len(fact_summary.issues),
            risk_count=len(fact_summary.reported_risks),
            generated_at=datetime.now(timezone.utc),
            llm_status=llm_status,
        )

    def _build_rule_based_findings(
        self,
        fact_summary: WeeklyScrumFactSummary,
    ) -> list[AiReviewFinding]:
        findings: list[AiReviewFinding] = []
        finding_seq = 1

        for delayed_task in fact_summary.delayed_tasks:
            evidence = [self._build_scrum_evidence_from_item(delayed_task)]

            if not self._contains_similar_task(
                delayed_task.title,
                fact_summary.next_week_tasks,
            ):
                findings.append(
                    AiReviewFinding(
                        finding_id=f"FIND-WEEKLY-{finding_seq:03d}",
                        type="MISSING_FOLLOW_UP",
                        title=f"미완료 업무 이월 누락 가능성: {delayed_task.title}",
                        description=(
                            "미완료 업무가 다음 주 계획에 명확히 포함되어 있지 않습니다."
                        ),
                        evidence=evidence,
                        impact="미완료 업무가 추적되지 않아 다음 주 일정에서 누락될 수 있습니다.",
                        recommended_action="다음 주 실행계획에 해당 업무를 이월할지 PM이 확인하세요.",
                        suggested_owner=delayed_task.owner
                        or delayed_task.source_member_name,
                        suggested_due_date=delayed_task.due_date,
                        confidence="HIGH",
                    )
                )
                finding_seq += 1

            if not delayed_task.owner:
                findings.append(
                    AiReviewFinding(
                        finding_id=f"FIND-WEEKLY-{finding_seq:03d}",
                        type="MISSING_OWNER",
                        title=f"미완료 업무 담당자 누락: {delayed_task.title}",
                        description="미완료 업무에 담당자가 명확히 지정되어 있지 않습니다.",
                        evidence=evidence,
                        impact="담당자가 없으면 후속 조치가 지연될 수 있습니다.",
                        recommended_action="PM이 담당자를 지정하거나 팀원에게 확인하세요.",
                        suggested_owner=delayed_task.source_member_name,
                        suggested_due_date=delayed_task.due_date,
                        confidence="MEDIUM",
                    )
                )
                finding_seq += 1

            if not delayed_task.due_date:
                findings.append(
                    AiReviewFinding(
                        finding_id=f"FIND-WEEKLY-{finding_seq:03d}",
                        type="MISSING_DUE_DATE",
                        title=f"미완료 업무 기한 누락: {delayed_task.title}",
                        description="미완료 업무에 다음 확인 기한 또는 완료 목표일이 없습니다.",
                        evidence=evidence,
                        impact="기한이 없으면 다음 주 진행 상황을 관리하기 어렵습니다.",
                        recommended_action="PM이 다음 확인 기한을 지정하세요.",
                        suggested_owner=delayed_task.owner
                        or delayed_task.source_member_name,
                        confidence="MEDIUM",
                    )
                )
                finding_seq += 1

        for issue in fact_summary.issues:
            has_response_plan = (
                self._contains_similar_task(issue.title, fact_summary.next_week_tasks)
                or bool(fact_summary.requests)
            )

            if not has_response_plan:
                findings.append(
                    AiReviewFinding(
                        finding_id=f"FIND-WEEKLY-{finding_seq:03d}",
                        type="MISSING_RESPONSE_PLAN",
                        title=f"이슈 대응 계획 누락 가능성: {issue.title}",
                        description="보고된 이슈에 대한 대응 계획이나 지원 요청이 명확하지 않습니다.",
                        evidence=[self._build_scrum_evidence_from_item(issue)],
                        impact="발생한 이슈가 다음 주에도 반복되거나 해결되지 않을 수 있습니다.",
                        recommended_action="이슈 해결을 위한 담당자, 대응 방안, 확인 일정을 정하세요.",
                        suggested_owner=issue.owner or issue.source_member_name,
                        suggested_due_date=issue.due_date,
                        confidence="HIGH",
                    )
                )
                finding_seq += 1

        for risk in fact_summary.reported_risks:
            evidence = [self._build_scrum_evidence_from_item(risk)]

            if not risk.owner:
                findings.append(
                    AiReviewFinding(
                        finding_id=f"FIND-WEEKLY-{finding_seq:03d}",
                        type="POTENTIAL_RISK",
                        title=f"위험 대응 담당자 확인 필요: {risk.title}",
                        description="보고된 위험에 대응 담당자가 명확히 지정되어 있지 않습니다.",
                        evidence=evidence,
                        impact="위험이 실제 이슈로 전환될 때 대응이 늦어질 수 있습니다.",
                        recommended_action="위험 대응 담당자를 지정하고 완화 방안을 정리하세요.",
                        suggested_owner=risk.source_member_name,
                        suggested_due_date=risk.due_date,
                        confidence="MEDIUM",
                    )
                )
                finding_seq += 1

            if not risk.due_date:
                findings.append(
                    AiReviewFinding(
                        finding_id=f"FIND-WEEKLY-{finding_seq:03d}",
                        type="MISSING_DUE_DATE",
                        title=f"위험 확인 기한 누락: {risk.title}",
                        description="보고된 위험에 확인 기한 또는 대응 목표일이 없습니다.",
                        evidence=evidence,
                        impact="위험 추적 주기가 불명확해질 수 있습니다.",
                        recommended_action="PM이 위험 확인 기한을 지정하세요.",
                        suggested_owner=risk.owner or risk.source_member_name,
                        confidence="MEDIUM",
                    )
                )
                finding_seq += 1

        if fact_summary.missing_update_members:
            findings.append(
                AiReviewFinding(
                    finding_id=f"FIND-WEEKLY-{finding_seq:03d}",
                    type="MISSING_RESPONSE_PLAN",
                    title="주간 스크럼 미제출 팀원 확인 필요",
                    description=(
                        "예상 팀원 중 주간 스크럼을 제출하지 않은 팀원이 있습니다: "
                        + ", ".join(fact_summary.missing_update_members)
                    ),
                    evidence=[
                        ScrumEvidence(
                            source_type="AI_INFERENCE",
                            text="expected_members와 member_updates를 비교하여 확인했습니다.",
                        )
                    ],
                    impact="팀 전체 진행 상황이 누락되어 보고서 정확도가 낮아질 수 있습니다.",
                    recommended_action="미제출 팀원의 주간 스크럼을 확인하세요.",
                    confidence="HIGH",
                )
            )

        return findings

    def _parse_llm_findings(
        self,
        data: dict,
        start_index: int,
    ) -> list[AiReviewFinding]:
        findings = []

        for index, item in enumerate(data.get("review_findings", []), start=start_index):
            try:
                payload = dict(item)
                payload["finding_id"] = f"FIND-WEEKLY-{index:03d}"
                llm_rule_code = payload.pop("rule_code", None)
                reference_ids = list(payload.get("reference_document_ids", []))
                if llm_rule_code and str(llm_rule_code).upper().startswith("REF"):
                    reference_ids.append(str(llm_rule_code))
                for evidence in payload.get("evidence", []):
                    document_id = evidence.get("document_id")
                    if document_id:
                        reference_ids.append(document_id)
                payload["rule_code"] = None
                payload["detection_source"] = "LLM"
                payload["reference_document_ids"] = list(dict.fromkeys(reference_ids))
                payload.setdefault("review_status", "PENDING")
                findings.append(AiReviewFinding(**payload))
            except Exception:
                continue

        return findings

    def review_weekly_scrum(
        self,
        request: WeeklyScrumReviewRequest,
    ) -> WeeklyScrumReviewResponse:
        analysis_date = request.analysis_date or request.week_end
        rule_findings = self._build_rule_based_findings(request.fact_summary)
        advanced_findings = self._build_advanced_rule_findings(
            request.fact_summary,
            analysis_date,
        )

        overdue_findings = self._build_overdue_findings(
            request.fact_summary,
            start_index=len(rule_findings) + len(advanced_findings) + 1,
            analysis_date=analysis_date,
        )

        llm_findings: list[AiReviewFinding] = []
        llm_status = "FALLBACK"

        if request.enable_llm and request.reference_documents:
            llm_result = self.llm_service.review_weekly_scrum_against_references(
                project_name=request.project_name,
                fact_summary=request.fact_summary,
                team_summary=request.team_summary,
                reference_documents=request.reference_documents,
            )

            if llm_result:
                llm_findings = self._parse_llm_findings(
                    llm_result,
                    start_index=(
                        len(rule_findings)
                        + len(advanced_findings)
                        + len(overdue_findings)
                        + 1
                    ),
                )
                llm_status = "SUCCEEDED"

        llm_findings = [
            finding
            for finding in llm_findings
            if not self._is_already_satisfied_finding(
                finding,
                request.fact_summary,
                request.team_summary,
            )
            and not self._is_invalid_missing_owner_finding(
                finding,
                request.fact_summary,
            )
        ]

        review_findings = (
            rule_findings
            + advanced_findings
            + overdue_findings
            + llm_findings
        )

        review_findings = self._deduplicate_findings(
            review_findings
        )

        review_findings = [
            self._normalize_finding_suggested_owner(
                finding,
                request.fact_summary,
            )
            for finding in review_findings
        ]

        review_findings = self._renumber_findings(
            review_findings
        )

        overall_status = self._determine_weekly_scrum_status(
            request.fact_summary,
            review_findings,
        )

        return WeeklyScrumReviewResponse(
            project_id=request.project_id,
            week_start=request.week_start,
            week_end=request.week_end,
            overall_status=overall_status,
            review_findings=review_findings,
            finding_count=len(review_findings),
            generated_at=datetime.now(timezone.utc),
            llm_status=llm_status,
        )

    def _renumber_findings(
        self,
        findings: list[AiReviewFinding],
    ) -> list[AiReviewFinding]:
        renumbered: list[AiReviewFinding] = []

        for index, finding in enumerate(findings, start=1):
            renumbered.append(
                finding.model_copy(
                    update={
                        "finding_id": f"FIND-WEEKLY-{index:03d}",
                    }
                )
            )

        return renumbered

    def _build_fallback_next_actions(
        self,
        fact_summary: WeeklyScrumFactSummary,
        review_findings: list[AiReviewFinding],
        next_week_start: date,
        next_week_end: date,
    ) -> list[NextWeekActionPlan]:
        actions: list[NextWeekActionPlan] = []
        action_seq = 1

        # 실제 업무 ID와 생성된 action ID의 연결 관계
        item_action_ids: dict[str, str] = {}

        # 1. 팀원이 직접 작성한 다음 주 업무를 action으로 변환
        for task in fact_summary.next_week_tasks:
            due_date = task.due_date
            reason = "팀원이 직접 작성한 다음 주 업무입니다."

            if (
                due_date
                and not (
                    next_week_start
                    <= due_date
                    <= next_week_end
                )
            ):
                due_date = None
                reason += (
                    " 입력 기한이 다음 주 범위를 벗어나 "
                    "PM 재설정이 필요합니다."
                )

            action_id = f"ACT-WEEKLY-{action_seq:03d}"

            owner_id, owner = self._select_action_owner(
                fact_summary,
                next_week_start,
                next_week_end,
                preferred_owner_id=(
                    task.owner_id
                    or task.source_member_id
                ),
                preferred_owner=(
                    task.owner
                    or task.source_member_name
                ),
                preferred_role=task.task_type,
            )

            action = NextWeekActionPlan(
                action_id=action_id,
                source_item_id=self._item_identity(task),
                title=task.title,
                owner_id=owner_id,
                owner=owner,
                due_date=due_date,
                priority=(
                    "HIGH"
                    if (
                        task.status == "BLOCKED"
                        or task.carryover_count >= 2
                    )
                    else "MEDIUM"
                ),
                done_condition=(
                    task.done_condition
                    or task.description
                ),
                reason=reason,
                source_finding_id=None,
                source_finding_ids=[],
                requirement_id=task.requirement_id,
                wbs_id=task.wbs_id,
                deliverable_id=task.deliverable_id,
            )

            actions.append(action)

            # 이후 dependency_action_ids를 생성할 수 있도록
            # 원본 업무 ID와 action ID를 연결한다.
            for identity in (
                task.item_id,
                task.source_reference_id,
                task.wbs_id,
            ):
                if identity:
                    item_action_ids[identity] = action_id

            action_seq += 1

        # 2. 팀원이 작성한 다음 주 업무 사이의 의존관계 연결
        for task, action in zip(
            fact_summary.next_week_tasks,
            actions,
        ):
            dependencies = [
                item_action_ids[dependency_id]
                for dependency_id in task.dependency_ids
                if dependency_id in item_action_ids
            ]

            if dependencies:
                updated_action = action.model_copy(
                    update={
                        "dependency_action_ids": dependencies,
                    }
                )

                action_index = actions.index(action)
                actions[action_index] = updated_action

        # 3. review finding을 실행 가능한 action으로 변환
        actionable_finding_types = {
            "MISSING_FOLLOW_UP",
            "MISSING_RESPONSE_PLAN",
            "POTENTIAL_RISK",
            "DEPENDENCY",
            "CONFLICT",
            "MISSING_OWNER",
            "MISSING_DUE_DATE",
            "MISSING_REQUIRED_WORK",
            "OVERDUE",
        }

        strict_role_rule_codes = {
            "MEMBER_OVERLOAD",
            "MISSING_INTEGRATION_TEST",
        }

        for finding in review_findings:
            if finding.type not in actionable_finding_types:
                continue

            preferred_role = self._preferred_role_for_finding(
                finding,
            )

            strict_role = (
                finding.rule_code
                in strict_role_rule_codes
            )

            owner_id, owner = self._select_action_owner(
                fact_summary,
                next_week_start,
                next_week_end,
                preferred_owner_id=(
                    finding.suggested_owner_id
                ),
                preferred_owner=(
                    finding.suggested_owner
                ),
                preferred_role=preferred_role,
                exclude_owner_id=(
                    finding.suggested_owner_id
                    if finding.rule_code
                    == "MEMBER_OVERLOAD"
                    else None
                ),
                strict_role=strict_role,
            )

            # 통합 테스트는 QA 또는 TEST 역할의 팀원만
            # 자동 담당자로 지정할 수 있다.
            #
            # _select_action_owner()가 다른 직군이나 PM을
            # 반환했다면 담당자를 비워서 PM 결정 대상으로 둔다.
            if (
                finding.rule_code
                == "MISSING_INTEGRATION_TEST"
                and owner_id
            ):
                selected_member = next(
                    (
                        member
                        for member
                        in fact_summary.team_members
                        if member.member_id == owner_id
                    ),
                    None,
                )

                selected_role = (
                    selected_member.role.upper()
                    if (
                        selected_member
                        and selected_member.role
                    )
                    else ""
                )

                if selected_role not in {
                    "QA",
                    "TEST",
                    "TESTER",
                }:
                    owner_id = None
                    owner = None

            suggested_due_date = (
                finding.suggested_due_date
            )

            if (
                suggested_due_date
                and (
                    next_week_start
                    <= suggested_due_date
                    <= next_week_end
                )
            ):
                due_date = suggested_due_date
            else:
                due_date = self._planned_due_date(
                    finding,
                    next_week_start,
                    next_week_end,
                )

            action = NextWeekActionPlan(
                action_id=(
                    f"ACT-WEEKLY-{action_seq:03d}"
                ),
                source_item_id=self._finding_action_item_id(finding),
                title=self._action_title_from_finding(
                    finding,
                ),
                owner_id=owner_id,
                owner=owner,
                due_date=due_date,
                priority=(
                    "HIGH"
                    if finding.confidence == "HIGH"
                    else "MEDIUM"
                ),
                done_condition=(
                    self._done_condition_from_finding(
                        finding,
                    )
                ),
                reason=(
                    finding.pm_modified_description
                    or finding.description
                ),
                source_finding_id=finding.finding_id,
                source_finding_ids=[
                    finding.finding_id,
                ],
            )

            actions.append(action)
            action_seq += 1

        # 4. 같은 업무의 일정 관련 action 통합
        actions = self._consolidate_schedule_actions(
            actions,
            review_findings,
        )

        # 5. 동일 선행 업무로 발생한 의존성 action 통합
        actions = self._consolidate_dependency_actions(
            actions,
            review_findings,
        )

        # 6. 통합이 끝난 action을 실제 업무 의존성과 연결
        actions = self._link_action_dependencies(
            actions,
            fact_summary,
            review_findings,
        )

        # 7. 통합 과정에서 비연속이 된 ID와 의존성 ID를 함께 다시 부여
        return self._renumber_actions(actions)

    def _finding_action_item_id(self, finding: AiReviewFinding) -> str | None:
        if (
            finding.rule_code == "BLOCKED_BY_UNFINISHED_DEPENDENCY"
            and finding.target_item_ids
        ):
            return finding.target_item_ids[-1]
        if finding.target_item_ids:
            return finding.target_item_ids[0]
        return next(
            (
                evidence.item_id
                or evidence.source_reference_id
                or evidence.wbs_id
                for evidence in finding.evidence
                if evidence.item_id or evidence.source_reference_id or evidence.wbs_id
            ),
            None,
        )

    def _link_action_dependencies(
        self,
        actions: list[NextWeekActionPlan],
        fact_summary: WeeklyScrumFactSummary,
        review_findings: list[AiReviewFinding],
    ) -> list[NextWeekActionPlan]:
        all_items = (
            fact_summary.completed_tasks
            + fact_summary.in_progress_tasks
            + fact_summary.delayed_tasks
            + fact_summary.issues
            + fact_summary.reported_risks
            + fact_summary.next_week_tasks
            + fact_summary.requests
        )
        items_by_id = {
            identity: item
            for item in all_items
            for identity in (item.item_id, item.source_reference_id, item.wbs_id)
            if identity
        }
        findings_by_id = {
            finding.finding_id: finding for finding in review_findings
        }
        actions_by_source: dict[str, tuple[int, str]] = {}
        for action in actions:
            if action.source_item_id:
                finding = findings_by_id.get(action.source_finding_id or "")
                rank = 1 if not finding else 2
                if finding and finding.rule_code == "BLOCKED_BY_UNFINISHED_DEPENDENCY":
                    rank = 0
                current = actions_by_source.get(action.source_item_id)
                if current is None or rank < current[0]:
                    actions_by_source[action.source_item_id] = (rank, action.action_id)

        linked: list[NextWeekActionPlan] = []
        for action in actions:
            item = items_by_id.get(action.source_item_id or "")
            dependency_ids = list(action.dependency_action_ids)
            if item:
                for dependency_item_id in item.dependency_ids:
                    dependency_match = actions_by_source.get(dependency_item_id)
                    dependency_action_id = (
                        dependency_match[1] if dependency_match else None
                    )
                    if (
                        dependency_action_id
                        and dependency_action_id != action.action_id
                        and dependency_action_id not in dependency_ids
                    ):
                        dependency_ids.append(dependency_action_id)
            linked.append(action.model_copy(update={
                "dependency_action_ids": dependency_ids,
            }))
        return linked

    def _renumber_actions(
        self,
        actions: list[NextWeekActionPlan],
    ) -> list[NextWeekActionPlan]:
        id_map = {
            action.action_id: f"ACT-WEEKLY-{index:03d}"
            for index, action in enumerate(actions, start=1)
        }
        return [
            action.model_copy(
                update={
                    "action_id": id_map[action.action_id],
                    "dependency_action_ids": [
                        id_map[action_id]
                        for action_id in action.dependency_action_ids
                        if action_id in id_map
                    ],
                }
            )
            for action in actions
        ]

    def _consolidate_dependency_actions(
        self,
        actions: list[NextWeekActionPlan],
        review_findings: list[AiReviewFinding],
    ) -> list[NextWeekActionPlan]:
        findings = {
            finding.finding_id: finding
            for finding in review_findings
        }

        result: list[NextWeekActionPlan] = []
        groups: dict[str, int] = {}
        affected_items_by_blocker: dict[str, list[str]] = {}

        def build_done_condition(
            blocker_id: str,
            affected_item_ids: list[str],
        ) -> str:
            affected_text = ", ".join(affected_item_ids)

            return (
                f"선행 업무 {blocker_id}가 완료되고 "
                f"후속 업무 {affected_text}의 착수 가능 여부가 확인됨"
            )

        for action in actions:
            finding = findings.get(action.source_finding_id or "")

            if (
                not finding
                or finding.rule_code
                != "BLOCKED_BY_UNFINISHED_DEPENDENCY"
            ):
                result.append(action)
                continue

            if not finding.target_item_ids:
                result.append(action)
                continue

            # target_item_ids 구조:
            # [후속 업무 ID, ..., 선행 업무 ID]
            blocker_id = finding.target_item_ids[-1]

            affected_item_ids = [
                item_id
                for item_id in finding.target_item_ids[:-1]
                if item_id and item_id != blocker_id
            ]

            # target_item_ids에 후속 업무가 없을 경우 evidence에서 복원
            if not affected_item_ids:
                affected_item_ids = [
                    evidence.item_id
                    for evidence in finding.evidence
                    if evidence.item_id
                    and evidence.item_id != blocker_id
                ]

            affected_item_ids = list(
                dict.fromkeys(affected_item_ids)
            )

            if blocker_id not in groups:
                groups[blocker_id] = len(result)
                affected_items_by_blocker[blocker_id] = list(
                    affected_item_ids
                )

                source_finding_ids = list(
                    action.source_finding_ids
                )

                if (
                    action.source_finding_id
                    and action.source_finding_id
                    not in source_finding_ids
                ):
                    source_finding_ids.append(
                        action.source_finding_id
                    )

                result.append(
                    action.model_copy(
                        update={
                            "title": (
                                "공통 선행 업무 완료 및 "
                                "후속 착수 조건 확인"
                            ),
                            "source_item_id": blocker_id,
                            "source_finding_ids": (
                                source_finding_ids
                            ),
                            "done_condition": build_done_condition(
                                blocker_id,
                                affected_item_ids,
                            ),
                        }
                    )
                )
                continue

            index = groups[blocker_id]
            current = result[index]

            merged_affected_items = list(
                dict.fromkeys(
                    affected_items_by_blocker[blocker_id]
                    + affected_item_ids
                )
            )
            affected_items_by_blocker[blocker_id] = (
                merged_affected_items
            )

            finding_ids = list(current.source_finding_ids)

            for finding_id in (
                action.source_finding_ids
                or [action.source_finding_id]
            ):
                if (
                    finding_id
                    and finding_id not in finding_ids
                ):
                    finding_ids.append(finding_id)

            merged_reason = self._merge_narrative_text(
                current.reason,
                action.reason,
            )

            result[index] = current.model_copy(
                update={
                    "title": (
                        "공통 선행 업무 완료 및 "
                        "후속 착수 조건 확인"
                    ),
                    "source_item_id": blocker_id,
                    "source_finding_ids": finding_ids,
                    "reason": merged_reason,
                    "done_condition": build_done_condition(
                        blocker_id,
                        merged_affected_items,
                    ),
                }
            )

        return result

    def _consolidate_schedule_actions(
        self,
        actions: list[NextWeekActionPlan],
        review_findings: list[AiReviewFinding],
    ) -> list[NextWeekActionPlan]:
        findings = {finding.finding_id: finding for finding in review_findings}
        result: list[NextWeekActionPlan] = []
        schedule_groups: dict[str, int] = {}
        schedule_types = {"MISSING_FOLLOW_UP", "MISSING_DUE_DATE", "OVERDUE"}

        for action in actions:
            finding = findings.get(action.source_finding_id or "")
            is_schedule_action = bool(
                finding
                and (
                    finding.type in schedule_types
                    or finding.rule_code == "REPEATED_CARRYOVER"
                )
            )
            target_id = None
            if finding:
                target_id = next(
                    (
                        evidence.item_id
                        or evidence.source_reference_id
                        or evidence.wbs_id
                        for evidence in finding.evidence
                        if (
                            evidence.item_id
                            or evidence.source_reference_id
                            or evidence.wbs_id
                        )
                    ),
                    None,
                )
                target_id = target_id or (
                    finding.target_item_ids[0]
                    if finding.target_item_ids
                    else None
                )

            if not is_schedule_action or not target_id:
                result.append(action)
                continue

            if target_id not in schedule_groups:
                schedule_groups[target_id] = len(result)
                result.append(action.model_copy(update={
                    "source_finding_ids": [action.source_finding_id]
                    if action.source_finding_id
                    else [],
                }))
                continue

            index = schedule_groups[target_id]
            current = result[index]
            finding_ids = list(current.source_finding_ids)
            if action.source_finding_id and action.source_finding_id not in finding_ids:
                finding_ids.append(action.source_finding_id)
            done_conditions = [
                value
                for value in (current.done_condition, action.done_condition)
                if value
            ]
            reasons = [
                value
                for value in (current.reason, action.reason)
                if value
            ]
            result[index] = current.model_copy(update={
                "title": "지연 원인 분석 및 일정·담당자 재확정",
                "due_date": min(
                    value
                    for value in (current.due_date, action.due_date)
                    if value
                ),
                "priority": "HIGH",
                "done_condition": " / ".join(dict.fromkeys(done_conditions)),
                "reason": " / ".join(dict.fromkeys(reasons)),
                "source_finding_ids": finding_ids,
            })

        return result

    def _preferred_role_for_finding(self, finding: AiReviewFinding) -> str | None:
        if finding.rule_code == "MISSING_INTEGRATION_TEST":
            return "QA"
        if finding.type == "DEPENDENCY":
            return finding.evidence[-1].role if finding.evidence else None
        return finding.evidence[0].role if finding.evidence else None

    def _member_available_for_window(
        self,
        member,
        next_week_start: date,
        next_week_end: date,
    ) -> bool:
        if member.availability_hours <= 0:
            return False
        if member.leave_start and member.leave_end:
            overlaps = not (
                member.leave_end < next_week_start
                or member.leave_start > next_week_end
            )
            if overlaps:
                return False
        return member.current_workload_hours < member.availability_hours

    def _select_action_owner(
        self,
        fact_summary: WeeklyScrumFactSummary,
        next_week_start: date,
        next_week_end: date,
        *,
        preferred_owner_id: str | None = None,
        preferred_owner: str | None = None,
        preferred_role: str | None = None,
        exclude_owner_id: str | None = None,
        strict_role: bool = False,
    ) -> tuple[str | None, str | None]:
        members = [
            member
            for member in fact_summary.team_members
            if member.member_id != exclude_owner_id
            and self._member_available_for_window(
                member,
                next_week_start,
                next_week_end,
            )
        ]

        normalized_role = (
            preferred_role or ""
        ).upper()

        role_aliases = {
            "FRONTEND": {"FRONTEND", "FE"},
            "BACKEND": {"BACKEND", "BE"},
            "QA": {"QA", "TEST"},
            "AI": {"AI"},
            "DATA": {"DATA"},
            "DEVOPS": {"DEVOPS"},
        }

        accepted_roles = role_aliases.get(
            normalized_role,
            {normalized_role},
        )

        def matches_preferred_role(member) -> bool:
            if not normalized_role:
                return True

            return (
                (member.role or "").upper()
                in accepted_roles
            )

        # ID가 존재하더라도 요구 역할과 일치할 때만 선택한다.
        for member in members:
            if (
                preferred_owner_id
                and member.member_id
                == preferred_owner_id
                and matches_preferred_role(member)
            ):
                return (
                    member.member_id,
                    member.member_name,
                )

        # 이름도 요구 역할과 일치할 때만 선택한다.
        for member in members:
            if (
                preferred_owner
                and member.member_name
                == preferred_owner
                and matches_preferred_role(member)
            ):
                return (
                    member.member_id,
                    member.member_name,
                )

        if (
            not normalized_role
            and not preferred_owner_id
            and not preferred_owner
        ):
            return None, None

        role_candidates = [
            member
            for member in members
            if matches_preferred_role(member)
        ]

        candidates = role_candidates

        if not candidates and strict_role:
            candidates = [
                member
                for member in members
                if (member.role or "").upper()
                in {
                    "PM",
                    "PROJECT_MANAGER",
                    "TEAM_LEAD",
                }
            ]
        elif not candidates:
            candidates = members

        if candidates:
            selected = min(
                candidates,
                key=lambda member: (
                    member.current_workload_hours
                    / member.availability_hours
                ),
            )

            return (
                selected.member_id,
                selected.member_name,
            )

        if exclude_owner_id:
            return None, None

        return None, None

    def _planned_due_date(
        self,
        finding: AiReviewFinding,
        next_week_start: date,
        next_week_end: date,
    ) -> date:
        offset = 2 if finding.confidence == "HIGH" else 4
        if finding.type in ("DEPENDENCY", "CONFLICT", "OVERDUE"):
            offset = 1
        return min(next_week_start + timedelta(days=offset), next_week_end)

    def _action_title_from_finding(self, finding: AiReviewFinding) -> str:
        if finding.pm_modified_title:
            return finding.pm_modified_title
        templates = {
            "TASK_STATUS_CONFLICT": "업무 상태 확인 및 기준 상태 확정",
            "BLOCKED_BY_UNFINISHED_DEPENDENCY": "선행 업무 완료 및 후속 착수 조건 확인",
            "UNKNOWN_DEPENDENCY": "선행 업무 상태와 담당자 확인",
            "REPEATED_CARRYOVER": "반복 이월 원인 분석 및 일정 재조정",
            "MISSING_INTEGRATION_TEST": "프론트·백엔드 통합 테스트 수행",
            "MEMBER_OVERLOAD": "업무 재배정 및 우선순위 조정",
        }
        return templates.get(finding.rule_code, finding.title)

    def _done_condition_from_finding(self, finding: AiReviewFinding) -> str | None:
        conditions = {
            "TASK_STATUS_CONFLICT": "관련 담당자가 실제 상태를 확인하고 단일 상태가 시스템에 반영됨",
            "BLOCKED_BY_UNFINISHED_DEPENDENCY": "선행 업무가 완료되고 후속 업무 착수 가능 여부가 확인됨",
            "UNKNOWN_DEPENDENCY": "선행 업무 ID, 상태, 담당자가 확인되어 연결 정보가 보완됨",
            "REPEATED_CARRYOVER": "지연 원인과 조정된 범위·담당자·기한이 PM 승인됨",
            "MISSING_INTEGRATION_TEST": "핵심 사용자 흐름의 프론트·백엔드 통합 테스트가 통과됨",
            "MEMBER_OVERLOAD": "가용 시간 안으로 업무량이 재조정되고 담당자가 확정됨",
        }
        return conditions.get(
            finding.rule_code,
            finding.pm_modified_action or finding.recommended_action,
        )

    def _parse_llm_next_actions(
        self,
        data: dict,
        fallback_actions: list[NextWeekActionPlan],
        next_week_start: date,
        next_week_end: date,
        valid_finding_ids: set[str],
    ) -> list[NextWeekActionPlan]:
        parsed_by_finding: dict[str, NextWeekActionPlan] = {}
        parsed_by_title: dict[str, NextWeekActionPlan] = {}

        for index, item in enumerate(
            data.get("recommended_next_actions", []),
            start=1,
        ):
            try:
                payload = dict(item)
                payload["action_id"] = payload.get(
                    "action_id",
                    f"ACT-WEEKLY-{index:03d}",
                )
                payload.setdefault("review_status", "PENDING")
                if payload.get("source_finding_id"):
                    payload.setdefault(
                        "source_finding_ids",
                        [payload["source_finding_id"]],
                    )
                action = NextWeekActionPlan(**payload)
                if (
                    action.source_finding_id
                    and action.source_finding_id not in valid_finding_ids
                ):
                    continue
                if action.source_finding_id:
                    parsed_by_finding.setdefault(action.source_finding_id, action)
                else:
                    parsed_by_title.setdefault(
                        " ".join(self._tokenize(action.title)),
                        action,
                    )
            except Exception:
                continue

        enriched: list[NextWeekActionPlan] = []
        for fallback in fallback_actions:
            llm_action = (
                parsed_by_finding.get(fallback.source_finding_id or "")
                if fallback.source_finding_id
                else parsed_by_title.get(" ".join(self._tokenize(fallback.title)))
            )
            if not llm_action:
                enriched.append(fallback)
                continue

            updates: dict = {}
            if self._is_executable_action_title(llm_action.title):
                updates["title"] = llm_action.title
            for field_name in (
                "owner_id",
                "owner",
                "priority",
                "done_condition",
                "reason",
            ):
                value = getattr(llm_action, field_name)
                if value is not None:
                    updates[field_name] = value
            if (
                llm_action.due_date
                and next_week_start <= llm_action.due_date <= next_week_end
            ):
                updates["due_date"] = llm_action.due_date

            effective_owner_id = updates.get("owner_id", fallback.owner_id)
            effective_owner = updates.get("owner", fallback.owner)
            updates["assignment_status"] = (
                "ASSIGNED"
                if effective_owner_id or effective_owner
                else "PM_DECISION_REQUIRED"
            )
            enriched.append(fallback.model_copy(update=updates))

        # LLM은 새로운 구조 객체를 만들지 않고 규칙 기반 action의 표현만 보강한다.
        return self._renumber_actions(enriched)

    def _is_executable_action_title(self, title: str) -> bool:
        normalized = title.replace(" ", "")
        risk_phrases = (
            "위험", "가능성", "우려", "미완료에따른", "인한", "따른",
        )
        action_phrases = (
            "수행", "확정", "점검", "조정", "확인", "완료", "보완",
            "재배정", "검증", "작성", "설정", "해결", "추가",
        )
        return (
            any(phrase in normalized for phrase in action_phrases)
            and not any(phrase in normalized for phrase in risk_phrases)
        )

    def recommend_next_actions(
        self,
        request: WeeklyScrumRecommendNextActionsRequest,
    ) -> WeeklyScrumRecommendNextActionsResponse:
        next_week_start = request.next_week_start or (request.week_end + timedelta(days=1))
        next_week_end = request.next_week_end or (next_week_start + timedelta(days=6))

        fallback_actions = self._build_fallback_next_actions(
            request.fact_summary,
            request.review_findings,
            next_week_start,
            next_week_end,
        )

        recommended_actions = fallback_actions
        llm_status = "FALLBACK"

        if request.enable_llm:
            llm_result = self.llm_service.recommend_next_actions(
                project_name=request.project_name,
                fact_summary=request.fact_summary,
                team_summary=request.team_summary,
                review_findings=request.review_findings,
                fallback_actions=fallback_actions,
                next_week_start=next_week_start,
                next_week_end=next_week_end,
            )

            if llm_result:
                recommended_actions = self._parse_llm_next_actions(
                    llm_result,
                    fallback_actions,
                    next_week_start,
                    next_week_end,
                    {finding.finding_id for finding in request.review_findings},
                )
                llm_status = "SUCCEEDED"

        return WeeklyScrumRecommendNextActionsResponse(
            project_id=request.project_id,
            week_start=request.week_start,
            week_end=request.week_end,
            next_week_start=next_week_start,
            next_week_end=next_week_end,
            recommended_next_actions=recommended_actions,
            action_count=len(recommended_actions),
            generated_at=datetime.now(timezone.utc),
            llm_status=llm_status,
        )

    def _is_included_action(self, action: NextWeekActionPlan) -> bool:
        return action.review_status in ("APPROVED", "MODIFIED")

    def _build_final_report_fallback(
        self,
        request: WeeklyScrumFinalizeRequest,
        included_findings: list[ReviewedAiReviewFinding],
        included_next_actions: list[NextWeekActionPlan],
    ) -> str:
        finding_lines = []
        for finding in included_findings:
            title = finding.pm_modified_title or finding.title
            description = finding.pm_modified_description or finding.description
            action = finding.pm_modified_action or finding.recommended_action

            finding_lines.append(
                f"{title}: {description}"
                + (f" 권고 조치: {action}" if action else "")
            )

        action_lines = []
        for action in included_next_actions:
            title = action.pm_modified_title or action.title
            owner = action.pm_modified_owner or action.owner
            due_date = action.pm_modified_due_date or action.due_date
            priority = action.pm_modified_priority or action.priority
            done_condition = (
                action.pm_modified_done_condition or action.done_condition
            )

            detail = []
            if owner:
                detail.append(f"담당자: {owner}")
            if due_date:
                detail.append(f"기한: {due_date}")
            if priority:
                detail.append(f"우선순위: {priority}")
            if done_condition:
                detail.append(f"완료 조건: {done_condition}")

            action_lines.append(
                title + (f" ({', '.join(detail)})" if detail else "")
            )

        completed_lines = [
            item.title for item in request.fact_summary.completed_tasks
        ]
        in_progress_lines = [
            item.title for item in request.fact_summary.in_progress_tasks
        ]
        delayed_lines = [
            item.title for item in request.fact_summary.delayed_tasks
        ]
        issue_lines = [
            item.title for item in request.fact_summary.issues
        ]
        risk_lines = [
            item.title for item in request.fact_summary.reported_risks
        ]

        return (
            f"{request.project_name or '프로젝트'} 최종 주간 프로젝트 상태 보고서입니다.\n\n"
            f"1. 핵심 요약\n"
            f"- {request.team_summary.executive_summary}\n\n"
            f"2. 사실 기반 업무 현황\n"
            f"2-1. 완료 업무\n"
            f"- "
            + ("\n- ".join(completed_lines) if completed_lines else "완료 업무 없음")
            + "\n\n"
            f"2-2. 진행 중 업무\n"
            f"- "
            + ("\n- ".join(in_progress_lines) if in_progress_lines else "진행 중 업무 없음")
            + "\n\n"
            f"2-3. 지연 업무\n"
            f"- "
            + ("\n- ".join(delayed_lines) if delayed_lines else "지연 업무 없음")
            + "\n\n"
            f"3. 사실 기반 이슈 및 위험\n"
            f"- 이슈: "
            + (", ".join(issue_lines) if issue_lines else "없음")
            + "\n"
            f"- 위험: "
            + (", ".join(risk_lines) if risk_lines else "없음")
            + "\n\n"
            f"4. 승인된 AI 검토 결과\n"
            f"- "
            + (
                "\n- ".join(finding_lines)
                if finding_lines
                else "승인된 AI 검토 결과 없음"
            )
            + "\n\n"
            f"5. PM 승인 다음 주 실행계획\n"
            f"- "
            + (
                "\n- ".join(action_lines)
                if action_lines
                else "PM이 승인한 다음 주 실행계획 없음"
            )
        )

    def finalize_weekly_scrum_report(
        self,
        request: WeeklyScrumFinalizeRequest,
    ) -> WeeklyScrumFinalizeResponse:
        included_findings = [
            finding
            for finding in request.reviewed_findings
            if finding.review_status in ("APPROVED", "MODIFIED")
        ]
        excluded_findings = [
            finding
            for finding in request.reviewed_findings
            if finding.review_status == "REJECTED"
        ]

        rejected_finding_ids = {
            finding.finding_id for finding in excluded_findings
        }

        def has_accepted_source(action: NextWeekActionPlan) -> bool:
            source_ids = list(action.source_finding_ids)
            if action.source_finding_id and action.source_finding_id not in source_ids:
                source_ids.append(action.source_finding_id)
            # 팀원이 직접 입력한 다음 주 업무처럼 finding과 무관한 action은 유지한다.
            return not source_ids or any(
                finding_id not in rejected_finding_ids for finding_id in source_ids
            )

        included_next_actions = []
        excluded_next_actions = []
        for action in request.recommended_next_actions:
            if self._is_included_action(action) and has_accepted_source(action):
                effective_owner_id = action.pm_modified_owner_id or action.owner_id
                effective_owner = action.pm_modified_owner or action.owner
                included_next_actions.append(action.model_copy(update={
                    "assignment_status": (
                        "ASSIGNED"
                        if effective_owner_id or effective_owner
                        else "PM_DECISION_REQUIRED"
                    ),
                    "effective_status": "INCLUDED",
                    "exclusion_reason": None,
                }))
                continue

            exclusion_reason = (
                "PM_REJECTED"
                if action.review_status == "REJECTED"
                else "ALL_SOURCE_FINDINGS_REJECTED"
            )
            excluded_next_actions.append(action.model_copy(update={
                "effective_status": "EXCLUDED",
                "exclusion_reason": exclusion_reason,
            }))

        final_report = self._build_final_report_fallback(
            request,
            included_findings,
            included_next_actions,
        )

        llm_status = "FALLBACK"

        if request.enable_llm:
            llm_result = self.llm_service.finalize_weekly_scrum_report(
                request=request,
                included_findings=included_findings,
                excluded_findings=excluded_findings,
                included_next_actions=included_next_actions,
                fallback_report=final_report,
            )

            if llm_result:
                llm_report = llm_result.get("final_report")
                if self._is_safe_llm_final_report(
                    llm_report,
                    excluded_findings,
                    excluded_next_actions,
                ):
                    final_report = llm_report
                    llm_status = "SUCCEEDED"

        return WeeklyScrumFinalizeResponse(
            project_id=request.project_id,
            week_start=request.week_start,
            week_end=request.week_end,
            included_findings=included_findings,
            excluded_findings=excluded_findings,
            included_next_actions=included_next_actions,
            excluded_next_actions=excluded_next_actions,
            final_report=final_report,
            generated_at=datetime.now(timezone.utc),
            llm_status=llm_status,
        )

    def _is_safe_llm_final_report(
        self,
        report: object,
        excluded_findings: list[ReviewedAiReviewFinding],
        excluded_actions: list[NextWeekActionPlan],
    ) -> bool:
        """거절·자동 제외된 항목이 LLM 최종문에 재등장하지 않게 한다."""
        if not isinstance(report, str) or not report.strip():
            return False

        excluded_titles = [
            finding.pm_modified_title or finding.title
            for finding in excluded_findings
        ] + [
            action.pm_modified_title or action.title
            for action in excluded_actions
        ]
        return not any(
            title and title in report
            for title in excluded_titles
        )

    def _is_already_satisfied_finding(
        self,
        finding: AiReviewFinding,
        fact_summary: WeeklyScrumFactSummary,
        team_summary: WeeklyTeamSummary,
    ) -> bool:
        # 이 함수는 순수 LLM finding 후처리 전용이다.
        # 규칙 finding 또는 이미 병합된 finding은 제거하지 않는다.
        if finding.detection_source != "LLM":
            return False

        def normalize(value: str | None) -> str:
            return (value or "").replace(" ", "").lower()

        title = normalize(finding.title)
        description = normalize(finding.description)
        recommended_action = normalize(finding.recommended_action)

        evidence_text = normalize(
            " ".join(
                evidence.text
                for evidence in finding.evidence
                if evidence.text
            )
        )

        evidence_member_names = normalize(
            " ".join(
                evidence.member_name
                for evidence in finding.evidence
                if evidence.member_name
            )
        )

        finding_text = (
            title
            + description
            + recommended_action
            + evidence_text
            + evidence_member_names
        )

        # fact_summary가 이미 존재하는데 LLM이
        # 사실 기반 통합 결과가 없다고 판단한 경우 제거한다.
        fact_summary_missing_keywords = (
            "사실요약누락",
            "사실기반요약누락",
            "통합요약누락",
            "fact_summary누락",
            "factsummary누락",
            "fact_summary없음",
            "factsummary없음",
        )

        if fact_summary and any(
            keyword in finding_text
            for keyword in fact_summary_missing_keywords
        ):
            return True

        # team_summary가 이미 존재하는데 LLM이
        # 팀 요약이 없다고 판단한 경우 제거한다.
        team_summary_missing_keywords = (
            "팀요약누락",
            "팀통합요약누락",
            "팀진행상황요약누락",
            "team_summary누락",
            "teamsummary누락",
            "team_summary없음",
            "teamsummary없음",
        )

        if team_summary and any(
            keyword in finding_text
            for keyword in team_summary_missing_keywords
        ):
            return True

        # 규칙 엔진이 missing_update_members를 기준으로 이미
        # 미제출 finding을 생성하므로 같은 팀원을 대상으로 하는
        # LLM finding은 중복으로 추가하지 않는다.
        if fact_summary.missing_update_members:
            missing_update_keywords = (
                "미제출",
                "업데이트누락",
                "업무진행상황미보고",
                "주간스크럼누락",
                "스크럼누락",
                "보고누락",
                "보고미제출",
                "missing_update",
                "missingupdate",
            )

            describes_missing_update = any(
                keyword in finding_text
                for keyword in missing_update_keywords
            )

            targets_known_missing_member = any(
                normalize(member_name) in finding_text
                for member_name in fact_summary.missing_update_members
                if normalize(member_name)
            )

            if (
                describes_missing_update
                and targets_known_missing_member
            ):
                return True

        return False

    def _normalize_finding_key(self, finding: AiReviewFinding) -> str:
        base_title = finding.title

        prefixes = [
            "미완료 업무 기한 누락:",
            "미완료 업무 담당자 누락:",
            "미완료 업무 이월 누락 가능성:",
            "위험 대응 담당자 확인 필요:",
            "위험 확인 기한 누락:",
            "이슈 대응 계획 누락 가능성:",
        ]

        for prefix in prefixes:
            if base_title.startswith(prefix):
                base_title = base_title.replace(prefix, "", 1).strip()
                break

        evidence_text = ""
        if finding.evidence:
            evidence_text = finding.evidence[0].text

        normalized = " ".join(
            self._tokenize(base_title + " " + evidence_text)
        )

        return f"{finding.type}:{normalized}"

    def _finding_priority(self, finding: AiReviewFinding) -> int:
        priority_map = {
            "POTENTIAL_RISK": 1,
            "CONFLICT": 2,
            "DEPENDENCY": 3,
            "MISSING_REQUIRED_WORK": 4,
            "MISSING_FOLLOW_UP": 5,
            "MISSING_RESPONSE_PLAN": 6,
            "OVERDUE": 7,
            "MISSING_OWNER": 8,
            "MISSING_DUE_DATE": 9,
            "NEEDS_CLARIFICATION": 10,
        }
        return priority_map.get(finding.type, 99)


    def _normalize_finding_target(self, finding: AiReviewFinding) -> str:
        structured_targets = sorted({
            target
            for evidence in finding.evidence
            for target in (
                evidence.source_reference_id,
                evidence.requirement_id,
                evidence.wbs_id,
                evidence.deliverable_id,
            )
            if target
        })
        if structured_targets:
            return "source:" + "|".join(structured_targets)

        text = finding.title

        removable_phrases = [
            "미완료 업무 기한 누락:",
            "미완료 업무 담당자 누락:",
            "미완료 업무 이월 누락 가능성:",
            "위험 대응 담당자 확인 필요:",
            "위험 확인 기한 누락:",
            "이슈 대응 계획 누락 가능성:",
            "과거 기한 확인 필요:",
            "작업 기한 미설정",
            "담당자 미지정",
            "담당자 미확인",
            "기한 미설정",
            "위험",
            "가능성",
            "확인 필요",
        ]

        for phrase in removable_phrases:
            text = text.replace(phrase, " ")

        if finding.evidence:
            text += " " + " ".join(evidence.text for evidence in finding.evidence)

        tokens = self._tokenize(text)
        unique_tokens = sorted(set(tokens))

        return " ".join(unique_tokens)


    def _merge_finding_details(
        self,
        primary: AiReviewFinding,
        duplicate: AiReviewFinding,
    ) -> AiReviewFinding:
        evidence = list(primary.evidence)

        existing_evidence_keys = {
            (
                item.source_type,
                item.member_id,
                item.document_id,
                item.text,
            )
            for item in evidence
        }

        for item in duplicate.evidence:
            key = (
                item.source_type,
                item.member_id,
                item.document_id,
                item.text,
            )
            if key not in existing_evidence_keys:
                evidence.append(item)
                existing_evidence_keys.add(key)

        impact = self._merge_narrative_text(primary.impact, duplicate.impact)
        recommended_action = self._merge_narrative_text(
            primary.recommended_action,
            duplicate.recommended_action,
        )

        confidence = primary.confidence
        if duplicate.confidence == "HIGH" or primary.confidence == "HIGH":
            confidence = "HIGH"
        elif duplicate.confidence == "MEDIUM" or primary.confidence == "MEDIUM":
            confidence = "MEDIUM"
        # 담당자 ID와 이름을 서로 다른 finding에서
        # 따로 가져오면 잘못된 조합이 만들어질 수 있다.
        #
        # 예:
        # primary: owner_id=None, owner="박승원"
        # duplicate: owner_id="BE-01", owner="정다영"
        #
        # 잘못된 병합:
        # owner_id="BE-01", owner="박승원"
        #
        # 따라서 ID와 이름을 하나의 쌍으로 취급한다.
        if (
            primary.suggested_owner_id
            or primary.suggested_owner
        ):
            suggested_owner_id = (
                primary.suggested_owner_id
            )
            suggested_owner = (
                primary.suggested_owner
            )
        else:
            suggested_owner_id = (
                duplicate.suggested_owner_id
            )
            suggested_owner = (
                duplicate.suggested_owner
            )
        suggested_due_date = primary.suggested_due_date or duplicate.suggested_due_date
        reference_document_ids = list(dict.fromkeys(
            primary.reference_document_ids + duplicate.reference_document_ids
        ))
        detection_source = primary.detection_source
        if primary.detection_source != duplicate.detection_source:
            detection_source = "RULE_AND_LLM"

        return primary.model_copy(
            update={
                "evidence": evidence,
                "impact": impact,
                "recommended_action": recommended_action,
                "confidence": confidence,
                "detection_source": detection_source,
                "reference_document_ids": reference_document_ids,
                "suggested_owner_id": suggested_owner_id,
                "suggested_owner": suggested_owner,
                "suggested_due_date": suggested_due_date,
            }
        )

    def _normalize_finding_suggested_owner(
        self,
        finding: AiReviewFinding,
        fact_summary: WeeklyScrumFactSummary,
    ) -> AiReviewFinding:
        """
        suggested_owner_id와 suggested_owner를
        fact_summary.team_members 기준으로 정규화한다.

        이름으로 팀원을 찾을 수 있으면 이름을 우선한다.
        이는 규칙 finding의 담당자 이름을 LLM의 잘못된 ID보다
        우선하기 위함이다.
        """
        members = fact_summary.team_members

        if not members:
            return finding

        # 이름으로 먼저 찾는다.
        if finding.suggested_owner:
            member_by_name = next(
                (
                    member
                    for member in members
                    if member.member_name
                    == finding.suggested_owner
                ),
                None,
            )

            if member_by_name:
                return finding.model_copy(
                    update={
                        "suggested_owner_id": (
                            member_by_name.member_id
                        ),
                        "suggested_owner": (
                            member_by_name.member_name
                        ),
                    }
                )

        # 이름으로 찾지 못했을 때만 ID로 찾는다.
        if finding.suggested_owner_id:
            member_by_id = next(
                (
                    member
                    for member in members
                    if member.member_id
                    == finding.suggested_owner_id
                ),
                None,
            )

            if member_by_id:
                return finding.model_copy(
                    update={
                        "suggested_owner_id": (
                            member_by_id.member_id
                        ),
                        "suggested_owner": (
                            member_by_id.member_name
                        ),
                    }
                )

        return finding

    def _merge_narrative_text(
        self,
        primary: str | None,
        supplemental: str | None,
    ) -> str | None:
        parts: list[str] = []
        for value in (primary, supplemental):
            if not value:
                continue
            for candidate in re.split(r"\s+/\s+|(?<=[.!?요다])\s+(?=[가-힣A-Z])", value):
                candidate = candidate.strip(" /\n")
                if not candidate:
                    continue
                candidate_tokens = set(self._tokenize(candidate))
                duplicate = False
                for current in parts:
                    current_tokens = set(self._tokenize(current))
                    union = candidate_tokens | current_tokens
                    similarity = (
                        len(candidate_tokens & current_tokens) / len(union)
                        if union else 1.0
                    )
                    if candidate == current or similarity >= 0.6:
                        duplicate = True
                        break
                if not duplicate:
                    parts.append(candidate)
        return " / ".join(parts) if parts else None


    def _deduplicate_findings(
        self,
        findings: list[AiReviewFinding],
    ) -> list[AiReviewFinding]:
        grouped: list[AiReviewFinding] = []

        for finding in findings:
            target_key = self._normalize_finding_target(finding)
            duplicate_index = None
            for index, current in enumerate(grouped):
                current_key = self._normalize_finding_target(current)
                if self._same_finding_root_cause(finding, current):
                    duplicate_index = index
                    break
                if target_key == current_key and finding.type == current.type:
                    duplicate_index = index
                    break

                target_tokens = set(self._tokenize(target_key))
                current_tokens = set(self._tokenize(current_key))
                union = target_tokens | current_tokens
                similarity = (
                    len(target_tokens & current_tokens) / len(union)
                    if union
                    else 0.0
                )
                if finding.type == current.type and similarity >= 0.55:
                    duplicate_index = index
                    break

            if duplicate_index is None:
                grouped.append(finding)
                continue

            current = grouped[duplicate_index]

            if (
                finding.detection_source in ("RULE", "RULE_AND_LLM")
                and current.detection_source == "LLM"
            ):
                grouped[duplicate_index] = self._merge_finding_details(
                    finding,
                    current,
                )
            elif (
                current.detection_source in ("RULE", "RULE_AND_LLM")
                and finding.detection_source == "LLM"
            ):
                grouped[duplicate_index] = self._merge_finding_details(
                    current,
                    finding,
                )
            elif self._finding_priority(finding) < self._finding_priority(current):
                grouped[duplicate_index] = self._merge_finding_details(
                    finding,
                    current,
                )
            else:
                grouped[duplicate_index] = self._merge_finding_details(
                    current,
                    finding,
                )

        return grouped

    def _same_finding_root_cause(
        self,
        left: AiReviewFinding,
        right: AiReviewFinding,
    ) -> bool:
        """규칙 탐지와 LLM 설명이 같은 원인을 말하면 새 finding 대신 보강한다."""
        # 서로 다른 결정적 규칙은 같은 업무를 가리켜도 별도 검토 의미를 가진다.
        # 원인 기반 교차 type 병합은 LLM 보강이 포함된 경우에만 수행한다.
        if (
            left.detection_source != "LLM"
            and right.detection_source != "LLM"
        ):
            return False
        left_targets = set(left.target_item_ids)
        right_targets = set(right.target_item_ids)
        for finding, targets in ((left, left_targets), (right, right_targets)):
            targets.update(
                value
                for evidence in finding.evidence
                for value in (
                    evidence.item_id,
                    evidence.source_reference_id,
                    evidence.wbs_id,
                )
                if value
            )
        if not left_targets.intersection(right_targets):
            return False

        def categories(finding: AiReviewFinding) -> set[str]:
            text = " ".join((
                finding.title,
                finding.description,
                finding.impact or "",
                finding.recommended_action or "",
            )).replace(" ", "").lower()
            values: set[str] = set()
            code_categories = {
                "MISSING_INTEGRATION_TEST": "integration",
                "BLOCKED_BY_UNFINISHED_DEPENDENCY": "dependency",
                "UNKNOWN_DEPENDENCY": "dependency",
                "REPEATED_CARRYOVER": "schedule",
                "MEMBER_OVERLOAD": "capacity",
            }
            if finding.rule_code in code_categories:
                # 명시적 규칙 코드는 설명 속 부수 단어보다 우선한다.
                return {code_categories[finding.rule_code]}
            keyword_categories = {
                "integration": ("통합테스트", "연동테스트", "integrationtest"),
                "dependency": ("선행업무", "의존", "착수조건", "스키마확정"),
                "schedule": ("지연", "이월", "기한", "일정"),
                "capacity": ("과부하", "가용시간", "업무량", "재배정"),
            }
            for category, keywords in keyword_categories.items():
                if any(keyword in text for keyword in keywords):
                    values.add(category)
            return values

        return bool(categories(left).intersection(categories(right)))

    def _build_overdue_findings(
        self,
        fact_summary: WeeklyScrumFactSummary,
        start_index: int,
        analysis_date: date,
    ) -> list[AiReviewFinding]:
        findings: list[AiReviewFinding] = []
        finding_seq = start_index

        check_targets = [
            ("진행 중 업무", fact_summary.in_progress_tasks),
            ("지연 업무", fact_summary.delayed_tasks),
            ("요청사항", fact_summary.requests),
        ]

        for section_name, items in check_targets:
            for item in items:
                if not item.due_date:
                    continue

                if item.due_date >= analysis_date:
                    continue

                findings.append(
                    AiReviewFinding(
                        finding_id=f"FIND-WEEKLY-{finding_seq:03d}",
                        type="OVERDUE",
                        title=f"과거 기한 확인 필요: {item.title}",
                        description=(
                            f"{section_name}의 기한이 분석 기준일({analysis_date})보다 이전입니다. "
                            "PM이 실제 완료 여부를 확인하거나 새 기한으로 조정해야 합니다."
                        ),
                        evidence=[
                            self._build_scrum_evidence_from_item(item)
                        ],
                        impact="지난 기한이 그대로 유지되면 다음 주 실행계획의 신뢰도가 낮아질 수 있습니다.",
                        recommended_action="PM이 완료 여부를 확인하고 필요하면 새 기한을 지정하세요.",
                        confidence="HIGH",
                        suggested_owner=item.owner or item.source_member_name,
                        suggested_due_date=None,
                    )
                )
                finding_seq += 1

        return findings

    def _find_similar_fact_item(
        self,
        title: str,
        fact_summary: WeeklyScrumFactSummary,
    ) -> ScrumItem | None:
        all_items = (
            fact_summary.completed_tasks
            + fact_summary.in_progress_tasks
            + fact_summary.delayed_tasks
            + fact_summary.issues
            + fact_summary.reported_risks
            + fact_summary.next_week_tasks
            + fact_summary.requests
        )

        title_tokens = set(self._tokenize(title))

        for item in all_items:
            item_tokens = set(self._tokenize(item.title))

            if title == item.title:
                return item

            if title_tokens and len(title_tokens & item_tokens) >= 2:
                return item

        return None

    def _is_invalid_missing_owner_finding(
        self,
        finding: AiReviewFinding,
        fact_summary: WeeklyScrumFactSummary,
    ) -> bool:
        if finding.type != "MISSING_OWNER":
            return False

        similar_item = self._find_similar_fact_item(
            finding.title,
            fact_summary,
        )

        if not similar_item:
            return False

        return bool(similar_item.owner or similar_item.source_member_name)
