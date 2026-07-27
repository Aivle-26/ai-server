from datetime import datetime
from urllib import request

from .schemas import (
    ActionItem,
    DeliverableRagRequest,
    DeliverableRagResponse,
    FinalReportRequest,
    FinalReportResponse,
    IssueRiskChangeCandidate,
    MeetingAnalysisRequest,
    MeetingAnalysisResponse,
    RagSource,
    WeeklyReportRequest,
    WeeklyReportResponse,
)
from .llm_service import ReportLlmService


class ReportService:
    def __init__(self) -> None:
        self.llm_service = ReportLlmService()

    def analyze_meeting(self, request: MeetingAnalysisRequest) -> MeetingAnalysisResponse:
        if request.enable_llm:
            llm_result = self.llm_service.analyze_meeting(request)
            if llm_result:
                return llm_result

        text = request.meeting_document.text

        action_items: list[ActionItem] = []
        if "김남효" in text:
            action_items.append(ActionItem(action_item="Report Agent 관련 작업 수행", owner="김남효"))
        if "정다영" in text:
            action_items.append(ActionItem(action_item="백엔드 API 연결 확인", owner="정다영"))
        if "확정" in text or "해야 한다" in text:
            action_items.append(ActionItem(action_item="회의에서 언급된 후속 작업 확정", owner=None))

        risks: list[IssueRiskChangeCandidate] = []
        if "담당자" in text and ("없" in text or "정해지지" in text):
            risks.append(IssueRiskChangeCandidate(
                risk_title="담당자 미지정 작업",
                risk_type="인력/역할 리스크",
                risk_level="MEDIUM",
                reason="회의록에 담당자가 정해지지 않은 작업이 언급되었습니다.",
            ))

        return MeetingAnalysisResponse(
            project_id=request.project_id,
            meeting_summary=text[:250],
            decision_logs=[],
            action_items=action_items,
            issue_risk_changes=risks,
            missing_owner_count=sum(1 for item in action_items if not item.owner),
            missing_due_date_count=sum(1 for item in action_items if not item.due_date),
            risk_missing_owner_count=sum(
                1 for risk in risks
                if "담당자" in risk.reason or "담당자" in risk.risk_title
            ),
            risk_missing_link_count=sum(
                1 for risk in risks
                if not risk.related_issue_id
                and not risk.related_requirement_id
                and not risk.related_wbs_id
            ),
            generated_at=datetime.now(),
            llm_status="FALLBACK",
        )

    def generate_weekly_report(self, request: WeeklyReportRequest) -> WeeklyReportResponse:
        if request.enable_llm:
            llm_result = self.llm_service.generate_weekly_report(request)
            if llm_result:
                return llm_result

        completed = [task.task_name for task in request.wbs_tasks if task.status == "DONE"]
        delayed = [
            task.task_name
            for task in request.wbs_tasks
            if task.status != "DONE" and task.due_date and task.due_date < request.week_end
        ]
        unassigned = [
            task.task_name
            for task in request.wbs_tasks
            if not task.assignee_id
        ]

        risks = [risk.risk_title for risk in request.open_risks]
        risks += [f"담당자 미지정 작업: {task_name}" for task_name in unassigned]

        progress_avg = (
            sum(task.progress_rate for task in request.wbs_tasks) / len(request.wbs_tasks)
            if request.wbs_tasks
            else 0
        )

        draft = (
            f"이번 주 프로젝트 평균 진행률은 {progress_avg:.1f}%입니다. "
            f"완료 작업은 {len(completed)}건, 지연 작업은 {len(delayed)}건, "
            f"담당자 미지정 작업은 {len(unassigned)}건, "
            f"관리 중인 리스크는 {len(risks)}건입니다."
        )

        return WeeklyReportResponse(
            project_id=request.project_id,
            week_start=request.week_start,
            week_end=request.week_end,
            progress_summary=f"평균 진행률 {progress_avg:.1f}%",
            completed_work=completed,
            delayed_work=delayed,
            risk_summary=risks,
            next_week_plan=["지연 작업 재점검", "미완료 액션 아이템 담당자 확인"],
            report_draft=draft,
            generated_at=datetime.now(),
            llm_status="FALLBACK",
        )

    def generate_final_report(self, request: FinalReportRequest) -> FinalReportResponse:
        if request.enable_llm:
            llm_result = self.llm_service.generate_final_report(request)
            if llm_result:
                return llm_result

        done_items = [item.item_name for item in request.execution_results if item.status == "DONE"]
        incomplete_items = [item.item_name for item in request.execution_results if item.status != "DONE"]
        remaining_risks = [risk.risk_title for risk in request.remaining_risks]

        draft = (
            f"프로젝트 최종 보고서 초안입니다. "
            f"완료 항목 {len(done_items)}건, 미완료 항목 {len(incomplete_items)}건, "
            f"잔여 리스크 {len(remaining_risks)}건이 확인되었습니다."
        )

        return FinalReportResponse(
            project_id=request.project_id,
            final_summary=draft,
            achievement_summary=done_items,
            incomplete_items=incomplete_items,
            remaining_risk_summary=remaining_risks,
            final_report_draft=draft,
            generated_at=datetime.now(),
            llm_status="FALLBACK",
        )

    def answer_deliverable_rag(self, request: DeliverableRagRequest) -> DeliverableRagResponse:
        matched_sources: list[RagSource] = []

        question_keywords = [
            word for word in request.question.replace("?", " ").replace(".", " ").split()
            if len(word) >= 2
        ]

        for doc in request.deliverable_documents:
            if any(keyword in doc.text for keyword in question_keywords):
                matched_sources.append(RagSource(
                deliverable_id=doc.deliverable_id,
                document_id=doc.document_id,
                document_name=doc.document_name,
                page=doc.page,
                excerpt=doc.text[:300],
                requirement_id=doc.requirement_id,
                wbs_id=doc.wbs_id,
                review_status=doc.review_status,
            ))

        if request.enable_llm:
            llm_result = self.llm_service.answer_deliverable_rag(request, matched_sources)
            if llm_result:
                return llm_result

        if matched_sources:
            answer = "관련 산출물 문서에서 질문과 연관된 내용을 찾았습니다. 근거 문서를 확인해 주세요."
        else:
            answer = "질문과 직접적으로 연결되는 산출물 근거를 찾지 못했습니다."

        return DeliverableRagResponse(
            project_id=request.project_id,
            answer=answer,
            sources=matched_sources,
            generated_at=datetime.now(),
            llm_status="FALLBACK",
        )
