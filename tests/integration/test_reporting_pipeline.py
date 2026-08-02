from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app
from tests.fixtures.reporting_samples import meeting_request


class ReportingApiPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_meeting_weekly_final_and_rag_pipeline(self):
        meeting_response = self.client.post(
            "/api/v1/reports/meeting/analyze",
            json=meeting_request(enable_llm=False).model_dump(mode="json"),
        )
        self.assertEqual(meeting_response.status_code, 200)
        meeting = meeting_response.json()
        self.assertEqual(meeting["llm_status"], "FALLBACK")
        self.assertGreaterEqual(len(meeting["action_items"]), 1)

        weekly_response = self.client.post(
            "/api/v1/reports/weekly/generate",
            json={
                "project_id": 7,
                "project_name": "AIPM",
                "week_start": "2026-07-20",
                "week_end": "2026-07-26",
                "wbs_tasks": [
                    {
                        "wbs_id": 1,
                        "task_name": "Reporting API",
                        "assignee_id": 1,
                        "due_date": "2026-07-24",
                        "status": "DONE",
                        "progress_rate": 100,
                    },
                    {
                        "wbs_id": 2,
                        "task_name": "Reporting UI",
                        "assignee_id": None,
                        "due_date": "2026-07-25",
                        "status": "IN_PROGRESS",
                        "progress_rate": 50,
                    },
                ],
                "completed_action_items": meeting["action_items"],
                "open_risks": meeting["issue_risk_changes"],
                "enable_llm": False,
            },
        )
        self.assertEqual(weekly_response.status_code, 200)
        weekly = weekly_response.json()
        self.assertEqual(weekly["llm_status"], "FALLBACK")
        self.assertEqual(weekly["completed_work"], ["Reporting API"])
        self.assertEqual(weekly["delayed_work"], ["Reporting UI"])

        final_response = self.client.post(
            "/api/v1/reports/final/generate",
            json={
                "project_id": 7,
                "project_name": "AIPM",
                "approved_reports": [
                    {
                        "report_id": "WEEKLY-1",
                        "report_title": "Weekly report",
                        "report_type": "WEEKLY",
                        "content": weekly["report_draft"],
                    }
                ],
                "execution_results": [
                    {
                        "item_id": "WBS-1",
                        "item_name": weekly["completed_work"][0],
                        "status": "DONE",
                    },
                    {
                        "item_id": "WBS-2",
                        "item_name": weekly["delayed_work"][0],
                        "status": "PARTIAL",
                    },
                ],
                "remaining_risks": meeting["issue_risk_changes"],
                "enable_llm": False,
            },
        )
        self.assertEqual(final_response.status_code, 200)
        final = final_response.json()
        self.assertEqual(final["llm_status"], "FALLBACK")
        self.assertEqual(final["achievement_summary"], ["Reporting API"])
        self.assertEqual(final["incomplete_items"], ["Reporting UI"])

        rag_response = self.client.post(
            "/api/v1/reports/deliverables/rag/query",
            json={
                "project_id": 7,
                "question": "project",
                "deliverable_documents": [
                    {
                        "deliverable_id": "FINAL-1",
                        "document_id": "DOC-1",
                        "document_name": "final-report.txt",
                        "text": (
                            "The project final report contains "
                            + final["final_report_draft"]
                        ),
                        "review_status": "APPROVED",
                    }
                ],
                "enable_llm": False,
            },
        )
        self.assertEqual(rag_response.status_code, 200)
        rag = rag_response.json()
        self.assertEqual(rag["llm_status"], "FALLBACK")
        self.assertEqual(len(rag["sources"]), 1)
        self.assertEqual(rag["sources"][0]["document_id"], "DOC-1")


if __name__ == "__main__":
    unittest.main()
