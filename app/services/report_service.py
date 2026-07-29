import re
from datetime import date, datetime
from sys import prefix

from app.schemas.report import (
    ActionItem,
    DeliverableRagRequest,
    DeliverableRagResponse,
    FinalReportRequest,
    FinalReportResponse,
    IssueRiskChangeCandidate,
    MeetingAnalysisRequest,
    MeetingAnalysisResponse,
    RagSource,
    SourceReference,
    WeeklyReportRequest,
    WeeklyReportResponse,
)
from app.services.report_llm_service import ReportLlmService


class ReportService:
    def __init__(self) -> None:
        self.llm_service = ReportLlmService()

    def _split_sentences(self, text: str) -> list[str]:
        normalized = re.sub(r"(다\.|요\.|함\.|한다\.)", r"\1\n", text)
        sentences = re.split(r"[\n\r]+", normalized)
        return [sentence.strip() for sentence in sentences if sentence.strip()]

    def _extract_due_date(self, sentence: str) -> date | None:
        match = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", sentence)
        if not match:
            match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", sentence)

        if not match:
            return None

        year, month, day = map(int, match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def _extract_id(self, sentence: str, prefix: str) -> str | None:
        match = re.search(rf"({prefix}-[A-Z0-9]+(?:-[A-Z0-9]+)*)", sentence)
        return match.group(1) if match else None

    def _build_source(self, request: MeetingAnalysisRequest, sentence: str) -> SourceReference:
        return SourceReference(
            document_id=request.meeting_document.document_id,
            document_name=request.meeting_document.file_name,
            page=None,
            excerpt=sentence,
        )

    def analyze_meeting(self, request: MeetingAnalysisRequest) -> MeetingAnalysisResponse:
        if request.enable_llm:
            llm_result = self.llm_service.analyze_meeting(request)
            if llm_result:
                return llm_result

        text = request.meeting_document.text
        sentences = self._split_sentences(text)

        action_items: list[ActionItem] = []
        risks: list[IssueRiskChangeCandidate] = []

        action_patterns = [
            r"(?P<owner>[가-힣]{2,4})[은는]\s*(?P<task>.+?(?:완료|확인|정리|준비|작성|구현|테스트|검토|확정)(?:한다|해야 한다|하기로 했다|한다\.|해야 한다\.)?)",
        ]

        for sentence in sentences:
            if self._is_irrelevant_sentence(sentence):
                continue

            requirement_id = self._extract_id(sentence, "REQ")
            wbs_id = self._extract_id(sentence, "WBS")
            due_date = self._extract_due_date(sentence)
            source = self._build_source(request, sentence)

            for pattern in action_patterns:
                match = re.search(pattern, sentence)
                if match:
                    owner = match.group("owner")
                    if not self._is_valid_owner(owner):
                        continue

                    task = match.group("task").strip()
                    action_items.append(
                        ActionItem(
                            action_item=task,
                            owner=owner,
                            due_date=due_date,
                            status="TODO",
                            related_requirement_id=requirement_id,
                            related_wbs_id=wbs_id,
                            source=source,
                        )
                    )
                    break

            if "담당자" in sentence and ("없" in sentence or "미정" in sentence or "정해지지" in sentence):
                risks.append(
                    IssueRiskChangeCandidate(
                        risk_title="담당자 미정 작업",
                        risk_type="인력/역할 리스크",
                        change_type="NEW",
                        risk_level="MEDIUM",
                        reason=sentence,
                        related_requirement_id=requirement_id,
                        related_wbs_id=wbs_id,
                        source=source,
                    )
                )

            if "마감일" in sentence and ("미정" in sentence or "확정되지" in sentence):
                risks.append(
                    IssueRiskChangeCandidate(
                        risk_title="마감일 미정 작업",
                        risk_type="일정 리스크",
                        change_type="NEW",
                        risk_level="MEDIUM",
                        reason=sentence,
                        related_requirement_id=requirement_id,
                        related_wbs_id=wbs_id,
                        source=source,
                    )
                )

            if "품질 리스크" in sentence or "산출물 검토" in sentence:
                risks.append(
                    IssueRiskChangeCandidate(
                        risk_title="산출물 검토 관련 품질 리스크",
                        risk_type="품질/산출물 리스크",
                        change_type="NEW",
                        risk_level="HIGH" if "담당자" in sentence and "없" in sentence else "MEDIUM",
                        reason=sentence,
                        related_requirement_id=requirement_id,
                        related_wbs_id=wbs_id,
                        source=source,
                    )
                )

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

    def _calculate_weighted_progress(self, request: WeeklyReportRequest) -> float:
        weighted_sum = 0.0
        total_weight = 0.0

        for task in request.wbs_tasks:
            weight = task.estimated_man_day or 1
            weighted_sum += task.progress_rate * weight
            total_weight += weight

        return weighted_sum / total_weight if total_weight else 0.0

    def generate_weekly_report(self, request: WeeklyReportRequest) -> WeeklyReportResponse:
        if request.enable_llm:
            llm_result = self.llm_service.generate_weekly_report(request)
            if llm_result:
                return llm_result

        completed = [
            f"{task.task_name} ({task.wbs_id})"
            for task in request.wbs_tasks
            if task.status == "DONE"
        ]

        completed += [
            f"{item.action_item} ({item.related_wbs_id or '액션 아이템'})"
            for item in request.completed_action_items
            if item.status == "DONE"
        ]

        today = date.today()

        delayed = [
            f"{task.task_name} ({task.wbs_id})"
            for task in request.wbs_tasks
            if task.status != "DONE" and task.due_date and task.due_date < today
        ]

        in_progress = [
            f"{task.task_name} ({task.wbs_id})"
            for task in request.wbs_tasks
            if task.status == "IN_PROGRESS"
        ]

        unassigned = [
            f"{task.task_name} ({task.wbs_id})"
            for task in request.wbs_tasks
            if not task.assignee_id
        ]

        risks = [risk.risk_title for risk in request.open_risks]
        risks += [f"담당자 미지정 작업: {task_name}" for task_name in unassigned]

        progress_avg = self._calculate_weighted_progress(request)

        next_week_plan = []
        next_week_plan += [f"진행 중 작업 점검: {task_name}" for task_name in in_progress]
        next_week_plan += [f"지연 작업 재점검: {task_name}" for task_name in delayed]
        next_week_plan += [f"담당자 배정 필요: {task_name}" for task_name in unassigned]

        if not next_week_plan:
            next_week_plan = ["완료 작업 검토 및 다음 단계 계획 수립"]

        draft = (
            f"이번 주 프로젝트 공수 가중 평균 진행률은 {progress_avg:.1f}%입니다. "
            f"완료 작업은 {len(completed)}건, 지연 작업은 {len(delayed)}건, "
            f"담당자 미지정 작업은 {len(unassigned)}건, "
            f"관리 중인 리스크는 {len(risks)}건입니다."
        )

        return WeeklyReportResponse(
            project_id=request.project_id,
            week_start=request.week_start,
            week_end=request.week_end,
            progress_summary=f"공수 가중 평균 진행률 {progress_avg:.1f}%",
            completed_work=completed,
            delayed_work=delayed,
            risk_summary=risks,
            next_week_plan=next_week_plan,
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

    def _tokenize(self, text: str) -> list[str]:
        stopwords = {"은", "는", "이", "가", "을", "를", "에", "의", "와", "과", "로", "으로", "누가", "언제", "까지"}
        tokens = re.findall(r"[가-힣A-Za-z0-9_-]{2,}", text)
        return [token for token in tokens if token not in stopwords]

    def answer_deliverable_rag(self, request: DeliverableRagRequest) -> DeliverableRagResponse:
        question_keywords = set(self._tokenize(request.question))
        scored_sources: list[tuple[int, RagSource]] = []

        for doc in request.deliverable_documents:
            sentences = self._split_sentences(doc.text)
            for sentence in sentences:
                if self._is_irrelevant_sentence(sentence):
                    continue

                sentence_keywords = set(self._tokenize(sentence))
                score = len(question_keywords & sentence_keywords)

                if score < 2:
                    continue

                scored_sources.append(
                    (
                        score,
                        RagSource(
                            deliverable_id=doc.deliverable_id,
                            document_id=doc.document_id,
                            document_name=doc.document_name,
                            page=doc.page,
                            excerpt=sentence[:300],
                            requirement_id=doc.requirement_id,
                            wbs_id=doc.wbs_id,
                            review_status=doc.review_status,
                        ),
                    )
                )

        scored_sources.sort(key=lambda item: item[0], reverse=True)
        matched_sources = [source for _, source in scored_sources[:3]]

        if request.enable_llm:
            llm_result = self.llm_service.answer_deliverable_rag(request, matched_sources)
            if llm_result:
                return llm_result

        if matched_sources:
            answer = "질문과 관련된 산출물 근거를 찾았습니다. 반환된 sources의 근거 문장을 확인해 주세요."
        else:
            answer = "질문과 직접적으로 연결되는 산출물 근거를 찾지 못했습니다."

        return DeliverableRagResponse(
            project_id=request.project_id,
            answer=answer,
            sources=matched_sources,
            generated_at=datetime.now(),
            llm_status="FALLBACK",
        )

    def _is_valid_owner(self, owner: str) -> bool:
        invalid_owners = {
            "작업", "기능", "문서", "보고서", "회의록", "산출물",
            "리스크", "담당자", "마감일", "결과", "로직"
        }
        return owner not in invalid_owners and 2 <= len(owner) <= 4

    def _is_irrelevant_sentence(self, sentence: str) -> bool:
        irrelevant_patterns = [
            "관련이 없다",
            "직접 관련이 없다",
            "무관",
            "해당 없음",
            "연관이 없다",
        ]
        return any(pattern in sentence for pattern in irrelevant_patterns)