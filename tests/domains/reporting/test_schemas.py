import unittest

from pydantic import ValidationError

from app.domains.reporting.schemas import (
    ActionItem,
    FinalReportRequest,
    IssueRiskChangeCandidate,
    MeetingDocument,
    DeliverableRagRequest,
    WeeklyReportRequest,
    WbsTaskSnapshot,
)


class ReportingSchemaTest(unittest.TestCase):
    def test_list_defaults_are_independent(self):
        first = MeetingDocument(
            document_id="D-1", file_name="one.txt", text="Meeting"
        )
        second = MeetingDocument(
            document_id="D-2", file_name="two.txt", text="Meeting"
        )
        first.attendees.append("Kim")

        self.assertEqual(first.attendees, ["Kim"])
        self.assertEqual(second.attendees, [])

    def test_action_and_risk_enums_are_enforced(self):
        with self.assertRaises(ValidationError):
            ActionItem(action_item="Task", status="WAITING")
        with self.assertRaises(ValidationError):
            IssueRiskChangeCandidate(
                risk_title="Risk",
                risk_type="Schedule",
                risk_level="CRITICAL",
                reason="Late",
            )
        with self.assertRaises(ValidationError):
            IssueRiskChangeCandidate(
                risk_title="Risk",
                risk_type="Schedule",
                change_type="DELETE",
                reason="Late",
            )

    def test_wbs_progress_bounds_and_status_are_validated(self):
        base = {
            "wbs_id": 1,
            "task_name": "Build API",
            "status": "TODO",
            "progress_rate": 0,
        }
        for changes in (
            {"progress_rate": -1},
            {"progress_rate": 101},
            {"status": "WAITING"},
        ):
            with self.subTest(changes=changes), self.assertRaises(
                ValidationError
            ):
                WbsTaskSnapshot.model_validate({**base, **changes})

    def test_cross_domain_ids_are_positive_integers(self):
        base = {
            "wbs_id": 1,
            "task_name": "Build API",
            "status": "TODO",
            "progress_rate": 0,
        }
        for changes in (
            {"wbs_id": "WBS-1"},
            {"wbs_id": 0},
            {"requirement_id": -1},
            {"assignee_id": "MEMBER-1"},
        ):
            with self.subTest(changes=changes), self.assertRaises(
                ValidationError
            ):
                WbsTaskSnapshot.model_validate({**base, **changes})

    def test_week_and_task_date_order_is_validated(self):
        with self.assertRaises(ValidationError):
            WeeklyReportRequest.model_validate(
                {
                    "project_id": 1,
                    "week_start": "2026-08-02",
                    "week_end": "2026-08-01",
                    "wbs_tasks": [],
                }
            )
        with self.assertRaises(ValidationError):
            WbsTaskSnapshot.model_validate(
                {
                    "wbs_id": 1,
                    "task_name": "Build API",
                    "status": "TODO",
                    "progress_rate": 0,
                    "start_date": "2026-08-02",
                    "due_date": "2026-08-01",
                }
            )

    def test_rag_requires_question_documents_and_positive_page(self):
        base = {
            "project_id": 1,
            "question": "What changed?",
            "deliverable_documents": [
                {
                    "deliverable_id": "D-1",
                    "document_id": "DOC-1",
                    "document_name": "report.txt",
                    "text": "Change summary",
                    "page": 1,
                }
            ],
        }
        for changes in (
            {"question": ""},
            {"deliverable_documents": []},
            {
                "deliverable_documents": [
                    {**base["deliverable_documents"][0], "page": 0}
                ]
            },
        ):
            with self.subTest(changes=changes), self.assertRaises(
                ValidationError
            ):
                DeliverableRagRequest.model_validate({**base, **changes})

    def test_final_report_rejects_invalid_report_and_execution_statuses(self):
        base = {
            "project_id": 7,
            "approved_reports": [
                {
                    "report_id": "R-1",
                    "report_title": "Report",
                    "report_type": "WEEKLY",
                    "content": "Content",
                }
            ],
            "execution_results": [
                {
                    "item_id": "I-1",
                    "item_name": "Item",
                    "status": "DONE",
                }
            ],
        }
        for changes in (
            {
                "approved_reports": [
                    {**base["approved_reports"][0], "report_type": "DAILY"}
                ]
            },
            {
                "execution_results": [
                    {**base["execution_results"][0], "status": "SKIPPED"}
                ]
            },
        ):
            with self.subTest(changes=changes), self.assertRaises(
                ValidationError
            ):
                FinalReportRequest.model_validate({**base, **changes})


if __name__ == "__main__":
    unittest.main()
