from __future__ import annotations

from app.domains.reporting.schemas import (
    DeliverableRagRequest,
    FinalReportRequest,
    MeetingAnalysisRequest,
    WeeklyReportRequest,
)


def meeting_request(*, enable_llm: bool = False, text: str | None = None):
    return MeetingAnalysisRequest.model_validate(
        {
            "project_id": 7,
            "project_name": "AIPM",
            "meeting_document": {
                "document_id": "DOC-1",
                "file_name": "meeting.txt",
                "meeting_title": "Weekly sync",
                "meeting_date": "2026-07-27",
                "attendees": ["Kim", "Lee"],
                "text": text
                or "김남효가 Report Agent 작업을 해야 한다. 담당자는 아직 정해지지 않았다.",
            },
            "enable_llm": enable_llm,
        }
    )


def weekly_request(*, enable_llm: bool = False):
    return WeeklyReportRequest.model_validate(
        {
            "project_id": 7,
            "project_name": "AIPM",
            "week_start": "2026-07-20",
            "week_end": "2026-07-26",
            "wbs_tasks": [
                {
                    "wbs_id": "WBS-1",
                    "task_name": "Completed API",
                    "status": "DONE",
                    "progress_rate": 100,
                    "due_date": "2026-07-24",
                    "assignee_id": "M-1",
                },
                {
                    "wbs_id": "WBS-2",
                    "task_name": "Delayed UI",
                    "status": "IN_PROGRESS",
                    "progress_rate": 40,
                    "due_date": "2026-07-25",
                    "assignee_id": None,
                },
            ],
            "completed_action_items": [],
            "open_risks": [
                {
                    "risk_title": "API dependency",
                    "risk_type": "외부 의존성 리스크",
                    "risk_level": "MEDIUM",
                    "reason": "Partner API is delayed",
                }
            ],
            "enable_llm": enable_llm,
        }
    )


def final_request(*, enable_llm: bool = False):
    return FinalReportRequest.model_validate(
        {
            "project_id": 7,
            "project_name": "AIPM",
            "approved_reports": [
                {
                    "report_id": "R-1",
                    "report_title": "Weekly 1",
                    "report_type": "WEEKLY",
                    "approved_at": "2026-07-20T10:00:00",
                    "content": "API completed",
                }
            ],
            "execution_results": [
                {
                    "item_id": "E-1",
                    "item_name": "Backend",
                    "status": "DONE",
                },
                {
                    "item_id": "E-2",
                    "item_name": "Frontend",
                    "status": "PARTIAL",
                },
            ],
            "remaining_risks": [],
            "enable_llm": enable_llm,
        }
    )


def rag_request(*, enable_llm: bool = False, question: str = "API status?"):
    return DeliverableRagRequest.model_validate(
        {
            "project_id": 7,
            "question": question,
            "deliverable_documents": [
                {
                    "deliverable_id": "D-1",
                    "document_id": "DOC-1",
                    "document_name": "requirements.txt",
                    "text": "The API status endpoint returns service health.",
                    "page": 2,
                    "requirement_id": "REQ-1",
                    "wbs_id": "WBS-1",
                    "review_status": "APPROVED",
                },
                {
                    "deliverable_id": "D-2",
                    "document_id": "DOC-2",
                    "document_name": "ui.txt",
                    "text": "The dashboard uses cards.",
                },
            ],
            "enable_llm": enable_llm,
        }
    )
