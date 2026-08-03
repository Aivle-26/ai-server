import unittest

from fastapi.testclient import TestClient

from app.main import app
from tests.fixtures.reporting_samples import (
    final_request,
    meeting_request,
    rag_request,
    weekly_request,
)


class ReportingRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_all_reporting_endpoints_return_fallback_contracts(self):
        cases = (
            (
                "/api/v1/reports/meeting/analyze",
                meeting_request().model_dump(mode="json"),
                "meeting_summary",
            ),
            (
                "/api/v1/reports/weekly/generate",
                weekly_request().model_dump(mode="json"),
                "report_draft",
            ),
            (
                "/api/v1/reports/final/generate",
                final_request().model_dump(mode="json"),
                "final_report_draft",
            ),
            (
                "/api/v1/reports/deliverables/rag/query",
                rag_request().model_dump(mode="json"),
                "answer",
            ),
        )
        for path, payload, required_field in cases:
            with self.subTest(path=path):
                response = self.client.post(path, json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["llm_status"], "FALLBACK")
                self.assertIn(required_field, response.json())
                self.assertTrue(
                    response.headers["content-type"].startswith(
                        "application/json"
                    )
                )

    def test_reporting_request_validation_returns_422(self):
        response = self.client.post(
            "/api/v1/reports/weekly/generate",
            json={
                "project_id": 7,
                "week_start": "2026-07-20",
                "week_end": "2026-07-26",
                "wbs_tasks": [
                    {
                        "wbs_id": 1,
                        "task_name": "Task",
                        "status": "INVALID",
                        "progress_rate": 0,
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
