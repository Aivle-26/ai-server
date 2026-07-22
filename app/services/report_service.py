"""Pure analysis services used by the AI workflows."""
from datetime import date
from typing import Any

from app.schemas.report import (
    ActionItemCandidate,
    DecisionLogCandidate,
    IssueRiskChangeCandidate,
    MeetingAnalysisRequest,
    MeetingAnalysisResponse,
    SourceReference,
)


class ReportService:
    def build_meeting_response(
        self,
        request: MeetingAnalysisRequest,
        llm_result: dict[str, Any],
        llm_status: str,
    ) -> MeetingAnalysisResponse:
        decision_logs = self._build_decision_logs(
            raw_items=llm_result.get("decision_logs", []),
            document_id=request.meeting_document.document_id,
            document_name=request.meeting_document.file_name,
        )

        action_items = self._build_action_items(
            raw_items=llm_result.get("action_items", []),
            document_id=request.meeting_document.document_id,
            document_name=request.meeting_document.file_name,
        )

        issue_risk_changes = self._build_issue_risk_changes(
            raw_items=llm_result.get("issue_risk_changes", []),
            document_id=request.meeting_document.document_id,
            document_name=request.meeting_document.file_name,
        )

        missing_owner_count = sum(1 for item in action_items if not item.owner)
        missing_due_date_count = sum(1 for item in action_items if not item.due_date)

        return MeetingAnalysisResponse(
            project_id=request.project_id,
            meeting_summary=llm_result.get("meeting_summary", ""),
            decision_logs=decision_logs,
            action_items=action_items,
            issue_risk_changes=issue_risk_changes,
            missing_owner_count=missing_owner_count,
            missing_due_date_count=missing_due_date_count,
            llm_status=llm_status,
        )

    def _build_source(
        self,
        document_id: str | None,
        document_name: str,
        excerpt: str | None,
    ) -> SourceReference:
        return SourceReference(
            document_id=document_id,
            document_name=document_name,
            page=None,
            excerpt=excerpt,
        )

    def _build_decision_logs(
        self,
        raw_items: list[dict[str, Any]],
        document_id: str | None,
        document_name: str,
    ) -> list[DecisionLogCandidate]:
        results: list[DecisionLogCandidate] = []

        for item in raw_items:
            results.append(
                DecisionLogCandidate(
                    decision_title=item.get("decision_title", "제목 없음"),
                    decision_detail=item.get("decision_detail", ""),
                    related_requirement_id=item.get("related_requirement_id"),
                    related_wbs_id=item.get("related_wbs_id"),
                    owner=item.get("owner"),
                    source=self._build_source(
                        document_id=document_id,
                        document_name=document_name,
                        excerpt=item.get("source_excerpt"),
                    ),
                )
            )

        return results

    def _build_action_items(
        self,
        raw_items: list[dict[str, Any]],
        document_id: str | None,
        document_name: str,
    ) -> list[ActionItemCandidate]:
        results: list[ActionItemCandidate] = []

        for item in raw_items:
            due_date = self._parse_date(item.get("due_date"))

            results.append(
                ActionItemCandidate(
                    action_item=item.get("action_item", "작업명 없음"),
                    owner=item.get("owner"),
                    due_date=due_date,
                    status=item.get("status", "TODO"),
                    related_requirement_id=item.get("related_requirement_id"),
                    related_wbs_id=item.get("related_wbs_id"),
                    source=self._build_source(
                        document_id=document_id,
                        document_name=document_name,
                        excerpt=item.get("source_excerpt"),
                    ),
                )
            )

        return results

    def _build_issue_risk_changes(
        self,
        raw_items: list[dict[str, Any]],
        document_id: str | None,
        document_name: str,
    ) -> list[IssueRiskChangeCandidate]:
        results: list[IssueRiskChangeCandidate] = []

        for item in raw_items:
            results.append(
                IssueRiskChangeCandidate(
                    risk_title=item.get("risk_title", "리스크 제목 없음"),
                    risk_type=item.get("risk_type", "기타"),
                    change_type=item.get("change_type", "NEW"),
                    risk_level=item.get("risk_level", "MEDIUM"),
                    reason=item.get("reason", ""),
                    related_issue_id=item.get("related_issue_id"),
                    related_requirement_id=item.get("related_requirement_id"),
                    related_wbs_id=item.get("related_wbs_id"),
                    source=self._build_source(
                        document_id=document_id,
                        document_name=document_name,
                        excerpt=item.get("source_excerpt"),
                    ),
                )
            )

        return results

    def _parse_date(self, value: str | None) -> date | None:
        if not value:
            return None

        try:
            return date.fromisoformat(value)
        except ValueError:
            return None