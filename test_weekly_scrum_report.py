from datetime import date
import unittest

from pydantic import ValidationError

from app.schemas.report import (
    AiReviewFinding,
    NextWeekActionPlan,
    ReferenceDocument,
    ReviewedAiReviewFinding,
    ReviewedNextWeekAction,
    ScrumEvidence,
    ScrumItem,
    TeamMemberCapacity,
    WeeklyMemberUpdate,
    WeeklyScrumFactSummary,
    WeeklyScrumFinalizeRequest,
    WeeklyScrumRecommendNextActionsRequest,
    WeeklyScrumReviewRequest,
    WeeklyScrumSummarizeRequest,
    WeeklyTeamSummary,
)
from app.services.report_service import ReportService


WEEK_START = date(2026, 7, 27)
WEEK_END = date(2026, 8, 2)


def team_summary() -> WeeklyTeamSummary:
    return WeeklyTeamSummary(
        overall_status="AT_RISK",
        executive_summary="일부 일정과 연동 위험을 확인해야 합니다.",
    )


class WeeklyScrumReportTest(unittest.TestCase):
    def setUp(self):
        self.service = ReportService()

    def test_summarize_preserves_cross_system_identifiers(self):
        request = WeeklyScrumSummarizeRequest(
            project_id=1,
            week_start=WEEK_START,
            week_end=WEEK_END,
            expected_members=["김남효", "정다영"],
            member_updates=[WeeklyMemberUpdate(
                member_id="member-ai-01",
                member_name="김남효",
                role="AI",
                in_progress_tasks=[ScrumItem(
                    item_id="SCRUM-001",
                    title="WBS 추출 API 구현",
                    owner="김남효",
                    due_date=date(2026, 8, 1),
                    status="IN_PROGRESS",
                    source_type="WBS_TASK",
                    source_reference_id="WBS-101",
                    requirement_id="REQ-001",
                    wbs_id="WBS-101",
                    deliverable_id="DEL-001",
                )],
            )],
            enable_llm=False,
        )

        response = self.service.summarize_weekly_scrum(request)
        item = response.fact_summary.in_progress_tasks[0]

        self.assertEqual(item.source_member_id, "member-ai-01")
        self.assertEqual(item.source_reference_id, "WBS-101")
        self.assertEqual(item.requirement_id, "REQ-001")
        self.assertEqual(item.wbs_id, "WBS-101")
        self.assertEqual(item.deliverable_id, "DEL-001")
        self.assertEqual(response.fact_summary.missing_update_members, ["정다영"])

    def test_review_uses_explicit_analysis_date(self):
        fact = WeeklyScrumFactSummary(in_progress_tasks=[ScrumItem(
            title="연동 테스트",
            owner="정다영",
            due_date=date(2026, 8, 1),
            status="IN_PROGRESS",
        )])
        request = WeeklyScrumReviewRequest(
            project_id=1,
            week_start=WEEK_START,
            week_end=WEEK_END,
            analysis_date=WEEK_END,
            fact_summary=fact,
            team_summary=team_summary(),
            enable_llm=False,
        )

        response = self.service.review_weekly_scrum(request)

        self.assertEqual(response.finding_count, 1)
        self.assertEqual(response.review_findings[0].type, "OVERDUE")
        self.assertIn("2026-08-02", response.review_findings[0].description)

    def test_recommendation_sanitizes_dates_and_converts_overdue(self):
        fact = WeeklyScrumFactSummary(next_week_tasks=[ScrumItem(
            title="Swagger 연동 테스트",
            owner="정다영",
            due_date=WEEK_END,
            status="TODO",
        )])
        overdue = AiReviewFinding(
            finding_id="FIND-WEEKLY-001",
            type="OVERDUE",
            title="과거 기한 확인 필요: 연동 테스트",
            description="기한이 지났습니다.",
            recommended_action="완료 여부를 확인하고 새 기한을 지정하세요.",
            confidence="HIGH",
            suggested_owner="정다영",
        )
        request = WeeklyScrumRecommendNextActionsRequest(
            project_id=1,
            week_start=WEEK_START,
            week_end=WEEK_END,
            fact_summary=fact,
            team_summary=team_summary(),
            review_findings=[overdue],
            enable_llm=False,
        )

        response = self.service.recommend_next_actions(request)

        self.assertEqual(response.next_week_start, date(2026, 8, 3))
        self.assertEqual(response.next_week_end, date(2026, 8, 9))
        self.assertIsNone(response.recommended_next_actions[0].due_date)
        self.assertIn("PM 재설정", response.recommended_next_actions[0].reason)
        self.assertTrue(any(
            action.source_finding_id == "FIND-WEEKLY-001"
            for action in response.recommended_next_actions
        ))

    def test_final_decisions_require_rejection_reason(self):
        with self.assertRaises(ValidationError):
            ReviewedAiReviewFinding(
                finding_id="FIND-1",
                type="POTENTIAL_RISK",
                title="연동 위험",
                description="연동 테스트가 필요합니다.",
                review_status="REJECTED",
            )

    def test_finalize_rejects_incomplete_decision_set(self):
        finding = ReviewedAiReviewFinding(
            finding_id="FIND-1",
            type="POTENTIAL_RISK",
            title="연동 위험",
            description="연동 테스트가 필요합니다.",
            review_status="APPROVED",
        )
        with self.assertRaises(ValidationError):
            WeeklyScrumFinalizeRequest(
                project_id=1,
                week_start=WEEK_START,
                week_end=WEEK_END,
                fact_summary=WeeklyScrumFactSummary(),
                team_summary=team_summary(),
                reviewed_findings=[finding],
                source_finding_count=2,
                source_action_count=0,
                enable_llm=False,
            )

    def test_finalize_applies_all_pm_action_modifications(self):
        action = ReviewedNextWeekAction(
            action_id="ACT-1",
            title="기존 업무",
            priority="MEDIUM",
            review_status="MODIFIED",
            pm_modified_title="통합 테스트 실행",
            pm_modified_owner="정다영",
            pm_modified_due_date=date(2026, 8, 7),
            pm_modified_priority="HIGH",
            pm_modified_done_condition="통합 테스트 통과",
            pm_modified_reason="연동 위험 완화",
        )
        request = WeeklyScrumFinalizeRequest(
            project_id=1,
            project_name="PM Agent",
            week_start=WEEK_START,
            week_end=WEEK_END,
            fact_summary=WeeklyScrumFactSummary(),
            team_summary=team_summary(),
            recommended_next_actions=[action],
            source_finding_count=0,
            source_action_count=1,
            enable_llm=False,
        )

        response = self.service.finalize_weekly_scrum_report(request)

        self.assertIn("통합 테스트 실행", response.final_report)
        self.assertIn("담당자: 정다영", response.final_report)
        self.assertIn("우선순위: HIGH", response.final_report)
        self.assertIn("완료 조건: 통합 테스트 통과", response.final_report)

    def test_semantically_similar_findings_are_merged(self):
        evidence = ScrumEvidence(
            source_type="WEEKLY_SCRUM",
            member_name="김남효",
            text="기준문서 검토 프롬프트 고도화가 필요하다.",
        )
        findings = [
            AiReviewFinding(
                finding_id="FIND-1",
                type="MISSING_DUE_DATE",
                title="미완료 업무 기한 누락: 기준문서 검토 프롬프트 고도화",
                description="기한이 없습니다.",
                evidence=[evidence],
            ),
            AiReviewFinding(
                finding_id="FIND-2",
                type="MISSING_DUE_DATE",
                title="기준문서 검토 프롬프트 고도화 기한 미설정",
                description="완료 목표일이 필요합니다.",
                evidence=[evidence],
            ),
        ]

        merged = self.service._deduplicate_findings(findings)

        self.assertEqual(len(merged), 1)

    def test_review_detects_status_conflict_and_unfinished_dependency(self):
        fact = WeeklyScrumFactSummary(
            completed_tasks=[ScrumItem(
                item_id="TASK-API",
                title="프로젝트 생성 API",
                status="DONE",
                owner="정다영",
            )],
            in_progress_tasks=[ScrumItem(
                item_id="TASK-API",
                title="프로젝트 생성 API",
                status="IN_PROGRESS",
                owner="정다영",
            ), ScrumItem(
                item_id="TASK-DASHBOARD",
                title="대시보드 연결",
                status="IN_PROGRESS",
                dependency_ids=["TASK-SCHEMA"],
                owner="윤명세",
            ), ScrumItem(
                item_id="TASK-SCHEMA",
                title="공통 데이터 스키마 확정",
                status="BLOCKED",
                owner="김남효",
            )],
        )
        request = WeeklyScrumReviewRequest(
            project_id=1,
            week_start=WEEK_START,
            week_end=WEEK_END,
            fact_summary=fact,
            team_summary=team_summary(),
            enable_llm=False,
        )

        response = self.service.review_weekly_scrum(request)
        rule_codes = {finding.rule_code for finding in response.review_findings}

        self.assertIn("TASK_STATUS_CONFLICT", rule_codes)
        self.assertIn("BLOCKED_BY_UNFINISHED_DEPENDENCY", rule_codes)

    def test_review_detects_missing_integration_test_and_repeated_carryover(self):
        fact = WeeklyScrumFactSummary(
            completed_tasks=[ScrumItem(
                item_id="FE-CREATE",
                title="프로젝트 생성 화면 구현",
                task_type="FRONTEND",
                status="DONE",
                integration_required=True,
                owner="윤명세",
            )],
            delayed_tasks=[ScrumItem(
                item_id="BE-CREATE",
                title="프로젝트 생성 API 구현",
                task_type="BACKEND",
                status="BLOCKED",
                integration_required=True,
                carryover_count=3,
                owner="정다영",
            )],
        )
        response = self.service.review_weekly_scrum(WeeklyScrumReviewRequest(
            project_id=1,
            week_start=WEEK_START,
            week_end=WEEK_END,
            fact_summary=fact,
            team_summary=team_summary(),
            enable_llm=False,
        ))
        rule_codes = {finding.rule_code for finding in response.review_findings}

        self.assertIn("MISSING_INTEGRATION_TEST", rule_codes)
        self.assertIn("REPEATED_CARRYOVER", rule_codes)

    def test_review_detects_overload_and_action_planner_reassigns_owner(self):
        fact = WeeklyScrumFactSummary(
            team_members=[
                TeamMemberCapacity(
                    member_id="BE-1",
                    member_name="정다영",
                    role="BACKEND",
                    availability_hours=40,
                    current_workload_hours=38,
                ),
                TeamMemberCapacity(
                    member_id="BE-2",
                    member_name="박승원",
                    role="BACKEND",
                    availability_hours=40,
                    current_workload_hours=10,
                ),
            ],
            next_week_tasks=[ScrumItem(
                item_id="BE-NEW",
                title="API 계약 확정",
                task_type="BACKEND",
                owner_id="BE-1",
                owner="정다영",
                estimated_hours=8,
                status="TODO",
                done_condition="OpenAPI 스키마 확정",
            )],
        )
        review = self.service.review_weekly_scrum(WeeklyScrumReviewRequest(
            project_id=1,
            week_start=WEEK_START,
            week_end=WEEK_END,
            fact_summary=fact,
            team_summary=team_summary(),
            enable_llm=False,
        ))
        overload = next(
            finding
            for finding in review.review_findings
            if finding.rule_code == "MEMBER_OVERLOAD"
        )

        recommendation = self.service.recommend_next_actions(
            WeeklyScrumRecommendNextActionsRequest(
                project_id=1,
                week_start=WEEK_START,
                week_end=WEEK_END,
                fact_summary=fact,
                team_summary=team_summary(),
                review_findings=[overload],
                enable_llm=False,
            )
        )
        overload_action = next(
            action
            for action in recommendation.recommended_next_actions
            if action.source_finding_id == overload.finding_id
        )

        self.assertEqual(overload_action.title, "업무 재배정 및 우선순위 조정")
        self.assertEqual(overload_action.owner_id, "BE-2")
        self.assertEqual(overload_action.owner, "박승원")
        self.assertIsNotNone(overload_action.due_date)

    def test_overload_action_is_not_reassigned_to_unrelated_qa_member(self):
        fact = WeeklyScrumFactSummary(team_members=[
            TeamMemberCapacity(
                member_id="FE-1", member_name="윤명세", role="FRONTEND",
                availability_hours=40, current_workload_hours=40,
            ),
            TeamMemberCapacity(
                member_id="QA-1", member_name="박승원", role="QA",
                availability_hours=40, current_workload_hours=5,
            ),
        ])
        finding = AiReviewFinding(
            finding_id="FIND-WEEKLY-001",
            rule_code="MEMBER_OVERLOAD",
            type="POTENTIAL_RISK",
            title="프론트엔드 담당자 과부하",
            description="가용 시간을 초과했습니다.",
            suggested_owner_id="FE-1",
            suggested_owner="윤명세",
            evidence=[ScrumEvidence(
                source_type="WEEKLY_SCRUM", member_id="FE-1",
                member_name="윤명세", role="FRONTEND", text="40/40시간",
            )],
        )

        response = self.service.recommend_next_actions(
            WeeklyScrumRecommendNextActionsRequest(
                project_id=1, week_start=WEEK_START, week_end=WEEK_END,
                fact_summary=fact, team_summary=team_summary(),
                review_findings=[finding], enable_llm=False,
            )
        )
        action = response.recommended_next_actions[0]

        self.assertIsNone(action.owner_id)
        self.assertIsNone(action.owner)

    def test_finalize_excludes_action_when_all_source_findings_are_rejected(self):
        rejected = ReviewedAiReviewFinding(
            finding_id="FIND-1", type="MISSING_REQUIRED_WORK",
            title="스크럼 미제출", description="업데이트가 없습니다.",
            review_status="REJECTED", review_comment="이미 별도 제출함",
        )
        linked_action = ReviewedNextWeekAction(
            action_id="ACT-1", title="미제출 스크럼 확인",
            source_finding_id="FIND-1", source_finding_ids=["FIND-1"],
            review_status="APPROVED",
        )
        request = WeeklyScrumFinalizeRequest(
            project_id=1, week_start=WEEK_START, week_end=WEEK_END,
            fact_summary=WeeklyScrumFactSummary(), team_summary=team_summary(),
            reviewed_findings=[rejected], recommended_next_actions=[linked_action],
            source_finding_count=1, source_action_count=1, enable_llm=False,
        )

        response = self.service.finalize_weekly_scrum_report(request)

        self.assertEqual(response.included_next_actions, [])
        self.assertEqual([a.action_id for a in response.excluded_next_actions], ["ACT-1"])
        self.assertEqual(response.excluded_next_actions[0].effective_status, "EXCLUDED")
        self.assertEqual(
            response.excluded_next_actions[0].exclusion_reason,
            "ALL_SOURCE_FINDINGS_REJECTED",
        )
        self.assertNotIn("미제출 스크럼 확인", response.final_report)

    def test_consolidated_action_ids_are_contiguous(self):
        fact = WeeklyScrumFactSummary(in_progress_tasks=[ScrumItem(
            item_id="TASK-1", title="연동 작업", owner="정다영",
            status="IN_PROGRESS",
        )])
        findings = [
            AiReviewFinding(
                finding_id="FIND-1", type="MISSING_DUE_DATE",
                title="기한 누락", description="기한이 없습니다.",
                target_item_ids=["TASK-1"],
            ),
            AiReviewFinding(
                finding_id="FIND-2", rule_code="REPEATED_CARRYOVER",
                type="POTENTIAL_RISK", title="반복 이월",
                description="반복 이월됐습니다.", target_item_ids=["TASK-1"],
            ),
        ]
        response = self.service.recommend_next_actions(
            WeeklyScrumRecommendNextActionsRequest(
                project_id=1, week_start=WEEK_START, week_end=WEEK_END,
                fact_summary=fact, team_summary=team_summary(),
                review_findings=findings, enable_llm=False,
            )
        )

        self.assertEqual(
            [action.action_id for action in response.recommended_next_actions],
            [f"ACT-WEEKLY-{index:03d}" for index in range(1, response.action_count + 1)],
        )

    def test_rule_finding_remains_structural_owner_when_llm_enriches_it(self):
        rule = AiReviewFinding(
            finding_id="FIND-1",
            rule_code="MISSING_INTEGRATION_TEST",
            type="MISSING_REQUIRED_WORK",
            title="통합 테스트 업무 누락",
            description="통합 테스트 계획이 없습니다.",
            target_item_ids=["TASK-BE", "TASK-FE"],
            evidence=[ScrumEvidence(
                source_type="WEEKLY_SCRUM", item_id="TASK-BE",
                text="연동 테스트를 하지 못했습니다.",
            )],
        )
        llm = AiReviewFinding(
            finding_id="FIND-2",
            rule_code=None,
            detection_source="LLM",
            reference_document_ids=["REF-001"],
            type="POTENTIAL_RISK",
            title="통합 테스트 미완료에 따른 위험",
            description="API 계약 오류가 발생할 수 있습니다.",
            impact="재작업 위험이 있습니다.",
            target_item_ids=["TASK-BE"],
            evidence=[ScrumEvidence(
                source_type="REFERENCE_DOCUMENT", document_id="REF-001",
                text="연동 기능은 통합 테스트를 거쳐야 합니다.",
            )],
        )

        second_llm = llm.model_copy(update={
            "finding_id": "FIND-3",
            "title": "통합 테스트 지연 위험",
            "description": "통합 테스트 일정에 추가 영향이 예상됩니다.",
        })
        merged = self.service._deduplicate_findings([rule, llm, second_llm])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].rule_code, "MISSING_INTEGRATION_TEST")
        self.assertEqual(merged[0].type, "MISSING_REQUIRED_WORK")
        self.assertEqual(merged[0].detection_source, "RULE_AND_LLM")
        self.assertEqual(merged[0].reference_document_ids, ["REF-001"])
        self.assertEqual(merged[0].target_item_ids, ["TASK-BE", "TASK-FE"])

    def test_llm_reference_id_is_not_accepted_as_rule_code(self):
        parsed = self.service._parse_llm_findings({"review_findings": [{
            "rule_code": "REF-001",
            "type": "POTENTIAL_RISK",
            "title": "통합 테스트 위험",
            "description": "기준문서상 통합 테스트가 필요합니다.",
            "evidence": [{
                "source_type": "REFERENCE_DOCUMENT",
                "document_id": "REF-001",
                "text": "연동 기능은 통합 테스트를 거쳐야 합니다.",
            }],
        }]}, start_index=1)

        self.assertEqual(parsed[0].rule_code, None)
        self.assertEqual(parsed[0].detection_source, "LLM")
        self.assertEqual(parsed[0].reference_document_ids, ["REF-001"])

    def test_llm_action_enriches_fallback_without_losing_structure(self):
        fallback = NextWeekActionPlan(
            action_id="ACT-WEEKLY-001",
            source_item_id="TASK-BE",
            title="프론트·백엔드 통합 테스트 수행",
            owner_id="QA-1",
            owner="박승원",
            source_finding_id="FIND-1",
            source_finding_ids=["FIND-1"],
            dependency_action_ids=["ACT-WEEKLY-009"],
            requirement_id="REQ-1",
            wbs_id="WBS-1",
        )
        llm_data = {"recommended_next_actions": [{
            "title": "API 응답 형식 미확정으로 인한 프론트엔드 연동 지연",
            "owner": "박승원",
            "due_date": "2026-08-06",
            "priority": "HIGH",
            "done_condition": "핵심 흐름 테스트 통과",
            "reason": "API 계약 위험을 줄입니다.",
            "source_finding_id": "FIND-1",
        }]}

        actions = self.service._parse_llm_next_actions(
            llm_data, [fallback], date(2026, 8, 3), date(2026, 8, 9), {"FIND-1"},
        )
        action = actions[0]

        self.assertEqual(action.title, fallback.title)
        self.assertEqual(action.source_item_id, "TASK-BE")
        self.assertEqual(action.source_finding_ids, ["FIND-1"])
        self.assertEqual(action.requirement_id, "REQ-1")
        self.assertEqual(action.wbs_id, "WBS-1")
        self.assertEqual(action.due_date, date(2026, 8, 6))

    def test_action_dependencies_are_linked_after_all_actions_are_created(self):
        fact = WeeklyScrumFactSummary(
            delayed_tasks=[ScrumItem(
                item_id="TASK-SCHEMA", title="스키마 확정", status="BLOCKED",
                owner="김남효",
            )],
            next_week_tasks=[ScrumItem(
                item_id="TASK-DASHBOARD", title="대시보드 연결", status="TODO",
                owner="윤명세", dependency_ids=["TASK-SCHEMA"],
            )],
        )
        finding = AiReviewFinding(
            finding_id="FIND-1", rule_code="REPEATED_CARRYOVER",
            type="POTENTIAL_RISK", title="반복 이월",
            description="스키마 업무가 반복 이월됐습니다.",
            target_item_ids=["TASK-SCHEMA"], suggested_owner="김남효",
        )

        response = self.service.recommend_next_actions(
            WeeklyScrumRecommendNextActionsRequest(
                project_id=1, week_start=WEEK_START, week_end=WEEK_END,
                fact_summary=fact, team_summary=team_summary(),
                review_findings=[finding], enable_llm=False,
            )
        )
        dashboard = next(
            action for action in response.recommended_next_actions
            if action.source_item_id == "TASK-DASHBOARD"
        )
        schema = next(
            action for action in response.recommended_next_actions
            if action.source_item_id == "TASK-SCHEMA"
        )

        self.assertEqual(dashboard.dependency_action_ids, [schema.action_id])

    def test_action_restores_source_item_id_from_finding_evidence(self):
        fact = WeeklyScrumFactSummary(in_progress_tasks=[ScrumItem(
            item_id="TASK-FE-PROJECT-CREATE",
            title="프로젝트 생성 화면 연동",
            status="IN_PROGRESS",
            owner_id="FE-01",
            owner="윤명세",
        )])
        finding = AiReviewFinding(
            finding_id="FIND-OVERDUE",
            type="OVERDUE",
            title="과거 기한 확인 필요: 프로젝트 생성 화면 연동",
            description="기한이 지났습니다.",
            evidence=[ScrumEvidence(
                source_type="WEEKLY_SCRUM",
                item_id="TASK-FE-PROJECT-CREATE",
                source_reference_id="PM-102",
                text="프로젝트 생성 화면 연동이 진행 중입니다.",
            )],
            suggested_owner_id="FE-01",
            suggested_owner="윤명세",
        )

        response = self.service.recommend_next_actions(
            WeeklyScrumRecommendNextActionsRequest(
                project_id=1,
                week_start=WEEK_START,
                week_end=WEEK_END,
                fact_summary=fact,
                team_summary=team_summary(),
                review_findings=[finding],
                enable_llm=False,
            )
        )
        action = next(
            action
            for action in response.recommended_next_actions
            if action.source_finding_id == "FIND-OVERDUE"
        )

        self.assertEqual(action.source_item_id, "TASK-FE-PROJECT-CREATE")

    def test_finalize_rejects_approved_ownerless_action(self):
        with self.assertRaises(ValidationError):
            WeeklyScrumFinalizeRequest(
                project_id=1, week_start=WEEK_START, week_end=WEEK_END,
                fact_summary=WeeklyScrumFactSummary(), team_summary=team_summary(),
                reviewed_findings=[],
                recommended_next_actions=[ReviewedNextWeekAction(
                    action_id="ACT-1", title="업무 재배정",
                    review_status="APPROVED",
                )],
                source_finding_count=0, source_action_count=1,
                enable_llm=False,
            )


if __name__ == "__main__":
    unittest.main()
